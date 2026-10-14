"""Observable facts, privacy, isolation and portable offline data contracts."""
import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from evidenceguard.ops import (Recorder, CTX, RECORDER, SCHEMA, canonical,
    model_post, prompt_snapshot, traced, validate_bundle)


@pytest.fixture
def anyio_backend(): return 'asyncio'


@pytest.fixture
def recorder(tmp_path):
    value=Recorder(tmp_path/'ops.sqlite3')
    yield value
    value.close()


def test_prompt_privacy_and_multimodal_omission():
    body={'model':'model-test','messages':[{'role':'system','content':'fixed rules'},
        {'role':'system','content':'private memory'}, {'role':'user','content':[
            {'type':'text','text':'my private question'}, {'type':'image_url','image_url':{'url':'data:image/jpeg;base64,NOTREAL'}}]}],
        'tools':[], 'api_key':'secretvalue'}
    redacted=canonical(prompt_snapshot(body))
    assert 'fixed rules' in redacted
    for value in ('private memory','my private question','NOTREAL','secretvalue'): assert value not in redacted
    captured=canonical(prompt_snapshot(body,True))
    assert 'my private question' in captured and 'NOTREAL' not in captured and 'secretvalue' not in captured


@pytest.mark.anyio
async def test_concurrent_traces_do_not_cross_and_usage_is_real(recorder):
    class Operation:
        ops=recorder
        @traced('chat')
        async def run(self):
            client=SimpleNamespace(post=AsyncMock(return_value=httpx.Response(200,json={
                'usage':{'prompt_tokens':12,'completion_tokens':4,'total_tokens':16},'choices':[]})))
            await asyncio.sleep(.001)
            await model_post(client,'https://example.invalid/chat/completions',headers={'Authorization':'Bearer DO-NOT-STORE'},
                json={'model':'test-model','messages':[{'role':'system','content':'fixed'}]})
    async def run(trace):
        token=CTX.set({'traceId':trace,'spanId':'root-'+trace})
        try: await Operation().run()
        finally: CTX.reset(token)
    await asyncio.gather(run('run-one'),run('run-two'))
    recorder.flush(); bundle=recorder.bundle()
    calls=[r for r in bundle['records'] if r['kind']=='model']
    assert {r['traceId'] for r in calls}=={'run-one','run-two'}
    assert len(calls)==2 and all(r['data']['usage']['total_tokens']==16 for r in calls)
    for call in calls:
        prompt=next(r for r in bundle['records'] if r['id']==call['data']['promptId'])
        assert prompt['traceId']==call['traceId'] and prompt['spanId']==call['spanId']
    assert 'DO-NOT-STORE' not in canonical(bundle)
    assert not CTX.get()


@pytest.mark.anyio
async def test_http_success_is_separate_from_validation_failure(recorder):
    class Invalid:
        ops=recorder
        @traced('video_verify')
        async def run(self):
            client=SimpleNamespace(post=AsyncMock(return_value=httpx.Response(200,json={'choices':[]})))
            for _ in range(2):
                await model_post(client,'https://example.invalid',headers={},json={'model':'test','messages':[]})
            raise ValueError('private raw model output')
    with pytest.raises(ValueError): await Invalid().run()
    recorder.flush(); rows=recorder.bundle()['records']
    assert len([r for r in rows if r['kind']=='model' and r['status']=='http_ok'])==2
    assert any(r['name']=='video_verify.finished' and r['status']=='failed' for r in rows)
    assert 'private raw model output' not in canonical(rows)
    assert all(r['data']['usage'] is None for r in rows if r['kind']=='model')


@pytest.mark.anyio
async def test_cancelled_model_attempt_is_recorded_and_context_restored(recorder):
    token=RECORDER.set(recorder)
    client=SimpleNamespace(post=AsyncMock(side_effect=asyncio.CancelledError()))
    try:
        with pytest.raises(asyncio.CancelledError):
            await model_post(client,'https://example.invalid',headers={},json={'model':'test'})
    finally: RECORDER.reset(token)
    recorder.flush()
    assert next(r for r in recorder.bundle()['records'] if r['kind']=='model')['status']=='cancelled'
    assert RECORDER.get() is None


def test_offline_round_trip_idempotence_conflict_and_validation(recorder):
    recorder.emit('agent.finished',status='completed',trace={'traceId':'run-1'},data={'password':'not-exported'})
    recorder.flush(); bundle=recorder.bundle(); validate_bundle(bundle)
    assert recorder.import_bundle(bundle)['imported']
    assert not recorder.import_bundle(bundle)['imported']
    assert recorder.imported(bundle['dataset']['id'])==bundle
    conflict=copy.deepcopy(bundle); conflict['records'][0]['status']='failed'
    with pytest.raises(ValueError,match='冲突'): recorder.import_bundle(conflict)
    duplicate=copy.deepcopy(bundle); duplicate['records']*=2
    with pytest.raises(ValueError,match='重复'): recorder.import_bundle(duplicate)
    invalid=copy.deepcopy(bundle); invalid['records'][0]['durationMs']=float('nan')
    with pytest.raises(ValueError): recorder.import_bundle(invalid)
    assert len(recorder.datasets())==1


def test_writer_failure_does_not_raise_from_business(recorder):
    with recorder.lock: recorder.db.execute('DROP TABLE records')
    recorder.emit('business.completed')
    assert recorder.flush() and recorder.write_errors==1


@pytest.fixture
def app(tmp_path,monkeypatch):
    monkeypatch.setenv('EG_OPS_ENABLED','1')
    monkeypatch.delenv('EG_ACCESS_TOKEN',raising=False)
    monkeypatch.delenv('EG_OPS_TOKEN',raising=False)
    monkeypatch.setenv('EG_OPS_DATABASE',str(tmp_path/'observability.sqlite3'))
    from evidenceguard.app import create_app
    return create_app(tmp_path/'business.sqlite3',start_worker=False)


def test_endpoints_client_allowlist_and_import_never_changes_business(app):
    with TestClient(app) as client:
        event=dict(id='event-1',name='capture.sampled',traceId='agent-1',spanId='client-span',parentSpanId='server-span',
            platform='ios',status='observed',requestId='capture-1',deviceId='sdk-one',appVersion='1.0/8')
        assert client.post('/api/ops/client-events',json=[event]).status_code==422
        headers={'X-EG-Installation-ID':'phone-one'}
        assert client.post('/api/ops/client-events',headers=headers,json=[event]).json()['accepted']==1
        assert client.post('/api/ops/client-events',headers=headers,json=[event | {'name':'fake_model'}]).status_code==422
        assert client.post('/api/ops/client-events',headers=headers,json=[event | {'data':{'secret':'value'}}]).status_code==422
        app.state.ops.flush()
        bundle=client.get('/api/ops/export').json()
        validate_bundle(bundle)
        row=next(r for r in bundle['records'] if r['source']=='client')
        assert row['traceId']=='agent-1' and row['parentSpanId']=='server-span'
        assert row['data']['appVersion']=='1.0/8'
        before=list(app.state.store.db.iterdump())
        assert client.post('/api/ops/import',json=bundle).status_code==200
        assert client.post('/api/ops/import',json=bundle).json()['imported'] is False
        assert list(app.state.store.db.iterdump())==before
        assert client.get('/api/ops/export',params={'dataset':bundle['dataset']['id']}).json()==bundle
        assert len(client.get('/api/ops/datasets').json())==1


def test_ops_access_requires_separate_secret_and_rejects_cross_origin(app,monkeypatch):
    monkeypatch.setenv('EG_OPS_TOKEN','dashboard-test-key-'+'a'*32)
    with TestClient(app) as client:
        assert client.get('/api/ops/snapshot').status_code==403
        headers={'X-EG-Ops-Token':'dashboard-test-key-'+'a'*32}
        assert client.get('/api/ops/snapshot',headers=headers).status_code==200
        assert client.post('/api/ops/import',headers=headers|{'Origin':'https://untrusted.invalid'},json={}).status_code==403
        assert client.post('/api/ops/import',headers=headers,content=b'bad-json').status_code==422


def test_disabled_ops_is_additive(tmp_path,monkeypatch):
    monkeypatch.delenv('EG_OPS_ENABLED',raising=False)
    from evidenceguard.app import create_app
    app=create_app(tmp_path/'db.sqlite3',start_worker=False)
    with TestClient(app) as client:
        assert client.get('/api/ops/snapshot').status_code==404
        assert client.post('/api/ops/client-events',json=[]).json()=={'accepted':0,'enabled':False}


def test_static_dashboard_route_and_separate_database(app,tmp_path,monkeypatch):
    # Also close this fixture app, since this test creates a second configured app.
    with TestClient(app): pass
    root=tmp_path/'web';root.mkdir();(root/'index.html').write_text('<html>shell</html>')
    monkeypatch.setenv('EG_WEB_ROOT',str(root))
    from evidenceguard.app import create_app
    another=create_app(tmp_path/'other.sqlite3',start_worker=False)
    with TestClient(another) as client:
        assert 'shell' in client.get('/dashboard').text
        assert client.get('/api/not-a-route').status_code==404


@pytest.mark.anyio
async def test_live_challenge_propagates_agent_trace(tmp_path,recorder):
    from evidenceguard.store import Store
    from evidenceguard.camera.live import LiveDevices, DeviceImport, SessionStart, Heartbeat
    from evidenceguard.camera.contracts import SnapshotKind
    import time
    store=Store(tmp_path/'live.sqlite3');store.ops=recorder
    live=LiveDevices(store)
    d=live.import_devices(DeviceImport(accountId='account',environment='PR',platform='web',devices=[
        {'sn':'T8171TEST001','model':'T8171','name':'test'}]),'browser')[0]
    session=live.start(SessionStart(deviceId=d['id'],platform='web'),'browser')
    current=live.sessions[session['id']]
    live.heartbeat(current,Heartbeat(state='streaming',sequence=1,frameAgeMs=0))
    t=CTX.set({'traceId':'agent-root','spanId':'capture-parent'})
    try:
        task=asyncio.create_task(live.snapshot(d['id'],SnapshotKind.LIVE,SimpleNamespace(request_id='capture-test',deadline=time.time()+1)))
        await asyncio.sleep(.01)
        command=live.commands(current)[0]
        assert command['traceId']=='agent-root' and command['parentSpanId']=='capture-parent'
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
    finally: CTX.reset(t); await live.shutdown();store.close()
