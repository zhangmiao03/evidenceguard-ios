"""Isolated fixtures, not evidence of physical camera or SDK validation."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from evidenceguard import ops
from evidenceguard.visual_skills.audit import GuardRun, event
from evidenceguard.visual_skills.harness import SceneHarness
from evidenceguard.vision.processing import LocalVision
from test_visual_scenes import env, selected, frame, CLIENT


@pytest.fixture
def observed(env, tmp_path, monkeypatch):
    monkeypatch.delenv('EG_DASHBOARD_CAPTURE_CONTENT', raising=False)
    recorder=ops.Recorder(tmp_path/'observations.db',capture=True)
    env[1].ops=recorder
    yield env,recorder
    recorder.close()


def rows(recorder):
    assert recorder.flush()
    assert recorder.write_errors == 0
    return sorted(recorder.bundle()['records'],key=lambda r:(r['data'].get('guardSequence',0),r['at']))


@pytest.mark.parametrize('case',['normal','capture_failed','invalid_frame','discarded','cancelled'])
def test_check_correlates_real_path_preserves_outcome_and_does_not_duplicate_calls(observed,case):
    env,recorder=observed
    async def check():
        scenes,store,captures,harness=env
        scene=await selected(env)
        await scenes.activate(scene['id'],CLIENT,scene['revision'])
        captures.capture.reset_mock()
        if case=='capture_failed': captures.capture.side_effect=OSError('secret error never captured')
        elif case=='cancelled': captures.capture.side_effect=asyncio.CancelledError()
        else: captures.capture.return_value=frame(store,key='current',source='fixture' if case=='invalid_frame' else 'official_live_ios')
        if case=='discarded':
            async def paused(*args):
                scenes.pause(scene['id'],CLIENT,scenes.get(scene['id'],CLIENT)['revision'])
                return dict(state='outside',regionClear=True,identityClear=False,viewMatchesReference=True,reason='区域为空')
            harness.observe.side_effect=paused
        if case=='cancelled':
            with pytest.raises(asyncio.CancelledError): await scenes.step()
        else: assert await scenes.step()
        captures.capture.assert_awaited_once()
        if case in {'capture_failed','invalid_frame','cancelled'}: harness.observe.assert_not_awaited()
        else: harness.observe.assert_awaited_once()
        assert ops.RECORDER.get() is None and ops.CTX.get()=={}
        saved=scenes.get(scene['id'],CLIENT)
        data=rows(recorder)
        assert len({r['traceId'] for r in data})==1
        finish=next(r for r in data if r['name']=='guard.finished')
        assert finish['data']['mode']=='live_guard'
        if case=='cancelled': assert finish['status']=='cancelled'
        elif case=='discarded':
            assert finish['data']['disposition']=='discarded'
            assert saved['status']=='draft'
        else:
            assert finish['data']['disposition']=='committed'
            assert finish['data']['resultState']==('confirmed' if case=='normal' else 'unknown')
            assert saved['lastGuardRunId']==finish['traceId']
        assert not store.evidence() and not scenes.proactive.messages(CLIENT)
        assert 'secret error' not in json.dumps(data)
        with recorder.lock:
            assert recorder.db.execute('select count(*) from critical_records').fetchone()[0]==len(data)
    asyncio.run(check())


@pytest.mark.parametrize('mode',['disabled','budget','completed','failure','cancelled'])
def test_aux_diagnostics_use_existing_single_inference_and_model_request(observed,mode):
    env,recorder=observed
    async def check():
        scenes,store,_,_=env
        scene=await selected(env)
        receipt=frame(store,key='new')
        harness=SceneHarness(SimpleNamespace(),SimpleNamespace(reserve=lambda *a,**kw:'budget exhausted' if mode=='budget' else None))
        value=dict(status='completed',version='test-version',depth={'status':'completed'},
            flow={'status':'skipped','code':'LIVE_SAMPLE_REQUIRED'},images=[{'label':'b 同帧相对逆深度','base64':'test-binary'}])
        local=SimpleNamespace(guard_enabled=mode!='disabled',analyze=AsyncMock(return_value=value),parts=LocalVision.parts)
        if mode=='failure':local.analyze.side_effect=OSError('private diagnostic')
        if mode=='cancelled':local.analyze.side_effect=asyncio.CancelledError()
        harness.local_vision=local
        port=SimpleNamespace(model='doubao-test',_request=AsyncMock(return_value={'content':json.dumps(dict(
            state='inside',regionClear=True,identityClear=False,viewMatchesReference=True,reason='无法确认目标'))}))
        harness.vision_port=lambda:port
        with GuardRun(store,scene,mode='stored_video_replay'):
            if mode in {'failure','cancelled'}:
                with pytest.raises(OSError if mode=='failure' else asyncio.CancelledError):
                    await harness.observe(scene,receipt,store)
            else:
                result=await harness.observe(scene,receipt,store)
                assert result['state']=='unknown'  # The existing identity gate remains authoritative.
        data=rows(recorder)
        pre=[r for r in data if r['name']=='guard.preprocessing'][-1]
        assert pre['status']==({'disabled':'skipped','budget':'skipped','completed':'completed','failure':'failed','cancelled':'cancelled'}[mode])
        if mode in {'disabled','budget'}:local.analyze.assert_not_awaited()
        else:local.analyze.assert_awaited_once()
        if mode in {'budget','failure','cancelled'}:port._request.assert_not_awaited()
        else:port._request.assert_awaited_once()
        assert 'test-binary' not in json.dumps(data)
        assert 'private diagnostic' not in json.dumps(data)
        if mode=='completed':assert pre['data']['flow']['code']=='LIVE_SAMPLE_REQUIRED'
    asyncio.run(check())


def test_observer_failure_and_private_content_cannot_change_business_context(monkeypatch):
    monkeypatch.delenv('EG_DASHBOARD_CAPTURE_CONTENT',raising=False)
    def broken(*a,**kw):raise OSError('disk broken')
    store=SimpleNamespace(ops=SimpleNamespace(emit=broken,capture=False))
    outer={'traceId':'outer'}
    token=ops.CTX.set(outer)
    try:
        with GuardRun(store,{'id':'scene'}) as run:
            event('preprocessing',reason='private',status='skipped')
            run.finish(disposition='committed')
        assert ops.CTX.get() is outer
        assert ops.RECORDER.get() is None
    finally:ops.CTX.reset(token)


def test_private_scope_overrides_capture_and_idle_poll_does_not_create_runs(observed):
    env,recorder=observed
    assert asyncio.run(env[0].step()) is False
    assert rows(recorder)==[]
    token=ops.PRIVATE_CONTENT.set(True)
    try:
        with GuardRun(env[1],{'id':'private-scene','plan':{'title':'private-person'}}):
            event('judgment',judgment={'reason':'private-person'})
    finally:ops.PRIVATE_CONTENT.reset(token)
    assert 'private-person' not in json.dumps(rows(recorder))
