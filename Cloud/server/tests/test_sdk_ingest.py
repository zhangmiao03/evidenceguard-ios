import asyncio
import base64
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from evidenceguard.app import create_app
from evidenceguard.camera.ingest import SDKBatch, SDKEvent, SDKIngest
from evidenceguard.personal import PersonalAgent, Preferences
from evidenceguard.store import Store
from evidenceguard.visual_review import VisualReview


def event(key='e1', at=None, image=True, **changes):
    # Byte validation is separate from the mocked semantic model.
    at=at or int(time.time()//10)*10-20
    return dict(eventId=key,deviceSn='T8214-TEST',model='T8214',deviceName='门铃',
                startMs=int(at*1000),endMs=int(at*1000),detectionType='motion',hasVideo=True,
                imageBase64=base64.b64encode(b'\xff\xd8\xfftest\xff\xd9').decode() if image else None) | changes


def environment(tmp_path):
    store=Store(tmp_path/'events.sqlite')
    provider=SimpleNamespace(ready=True,model='test',base='test',describe_observations=AsyncMock(return_value=dict(visible='门口有纸箱',uncertainties='无法判断前后动作')))
    visual=VisualReview(store,provider); personal=PersonalAgent(store)
    personal.engine=SimpleNamespace(enqueue=lambda *args: None)
    return store,provider,visual,SDKIngest(store,visual,personal)


def test_authenticated_batch_is_idempotent_and_metadata_can_gain_image(tmp_path,monkeypatch):
    monkeypatch.setenv('EG_ACCESS_TOKEN','x'*40)
    app=create_app(tmp_path/'api.sqlite',start_worker=False)
    with TestClient(app) as client:
        body=dict(events=[event(image=False)])
        assert client.post('/api/sdk/events',json=body).status_code==401
        client.headers.update({'Authorization':'Bearer '+'x'*40,'X-EG-Installation-ID':str(uuid4())})
        first=client.post('/api/sdk/events',json=body)
        assert first.status_code==202 and first.json()['continuousCoverage'] is False
        assert first.json()['receipts'][0]['imageSaved'] is False
        body=dict(events=[event()],reviewRequested=True)
        second=client.post('/api/sdk/events',json=body)
        assert second.status_code==202 and second.json()['receipts'][0]['imageSaved']
        duplicate=client.post('/api/sdk/events',json=body)
        assert duplicate.json()['receipts'][0]['status']=='duplicate'
        evidence=app.state.store.evidence()
        assert len(evidence)==1 and evidence[0]['sourceType']=='official_sdk'
        assert evidence[0]['skillId']=='' and evidence[0]['relation']=='unknown'
        assert client.get(evidence[0]['imageUrl']).status_code==200
        assert app.state.store.skills()==[]  # An import must never arm a camera.


def test_bad_source_times_conflicts_and_partial_batches_are_rejected(tmp_path):
    s,p,v,i=environment(tmp_path)
    for bad in [event(imageSource='cached_cover'),event(startMs=-1),event(endMs=int((time.time()+600)*1000)),event(model='T9999')]:
        with pytest.raises(ValueError): SDKBatch.model_validate(dict(events=[bad]))
    with pytest.raises(ValueError):
        i.accept(SDKBatch.model_validate(dict(events=[event(),event('bad',imageBase64='/tmp/photo.jpg')])),'client')
    assert s.evidence()==[]
    first=event(); i.accept(SDKBatch.model_validate(dict(events=[first])),'client')
    with pytest.raises(ValueError):
        i.accept(SDKBatch.model_validate(dict(events=[event('new'),first | {'hasVideo':False}])),'client')
    assert len(s.evidence())==1
    s.close()


def test_nearby_events_are_one_multimage_call_and_cached_reviews_are_free(tmp_path):
    async def check():
        s,p,v,i=environment(tmp_path); now=time.time()
        start=int(now//10)*10-20
        i.accept(SDKBatch.model_validate(dict(events=[event('a',start),event('b',start+3),event('c',start+6)],reviewRequested=True)),'client',now)
        assert not await i.step(now+9)
        assert await i.step(now+11)
        assert p.describe_observations.await_count==1
        assert len(p.describe_observations.await_args.args[0])==3
        ep=i.status()['episodes'][0]
        assert ep['status']=='completed' and len(s.evidence())==3
        assert v.usage(ep['cameraId'])['requests']==1
        sources=i.events(ep['id'])
        await v.review(ep['cameraId'],ep['id'],[(e['imageUrl'].split('/')[-1],e['metadata']['startMs']/1000) for e in sorted(sources,key=lambda e:e['metadata']['startMs'])])
        assert p.describe_observations.await_count==1
        assert s.skills()==[] and all(e['relation']=='unknown' for e in s.evidence())
        s.close()
    asyncio.run(check())


def test_budget_failure_and_missing_images_never_become_success(tmp_path):
    async def check():
        s,p,v,i=environment(tmp_path); now=time.time()
        i.accept(SDKBatch.model_validate(dict(events=[event()],reviewRequested=True)),'client',now)
        p.describe_observations.side_effect=RuntimeError('provider token must stay hidden')
        await i.step(now+11); await i.step(now+42)
        ep=i.status()['episodes'][0]
        assert ep['status']=='unavailable' and p.describe_observations.await_count==2
        assert 'token' not in str(i.status())
        refs=[(i.events()[0]['imageUrl'].split('/')[-1],1)]
        assert (await v.review(ep['cameraId'],ep['id'],refs))['status']=='budget_exhausted'
        assert p.describe_observations.await_count==2
        v.DAILY_LIMIT=2
        assert v.reserve(ep['cameraId'],'another') is not None
        assert all(e['relation']=='unknown' for e in s.evidence())
        s.close()
    asyncio.run(check())


def test_unsupported_types_and_metadata_only_imports_do_not_call_model(tmp_path):
    async def check():
        s,p,v,i=environment(tmp_path); now=time.time()
        i.accept(SDKBatch.model_validate(dict(events=[event('a',detectionType='unknown'),event('b',image=False)],reviewRequested=True)),'client',now)
        await i.step(now+11)
        assert {e['status'] for e in i.status()['episodes']}=={'filtered','unavailable'}
        p.describe_observations.assert_not_awaited()
        s.close()
    asyncio.run(check())


def test_new_evidence_during_analysis_invalidates_old_result(tmp_path):
    async def check():
        s,p,v,i=environment(tmp_path); now=time.time(); at=int(now//10)*10-20
        i.accept(SDKBatch.model_validate(dict(events=[event('a',at)],reviewRequested=True)),'client',now)
        async def changed(frames):
            i.accept(SDKBatch.model_validate(dict(events=[event('b',at+3)],reviewRequested=True)),'client',now+12)
            return dict(visible='旧图',uncertainties='未知')
        p.describe_observations.side_effect=changed
        await i.step(now+11)
        ep=i.status()['episodes'][0]
        assert ep['status']=='pending' and ep['revision']==2
        assert all('旧图' not in e['reason'] for e in s.evidence())
        s.close()
    asyncio.run(check())


def test_ingest_to_proactive_message_reuses_review_and_has_openable_evidence(tmp_path):
    from test_harness import ScriptedProvider, tool
    p=ScriptedProvider([])
    app=create_app(tmp_path/'pipeline.sqlite',start_worker=False,provider=p)
    client_id=str(uuid4()); now=time.time()
    app.state.visual_review.provider=SimpleNamespace(ready=True,model='test',base='test',
        describe_observations=AsyncMock(return_value=dict(visible='事件图中有包裹',uncertainties='没有连续录像')))
    with TestClient(app) as client:
        client.headers['X-EG-Installation-ID']=client_id
        client.put('/api/personal/preferences',json=dict(enabled=True,quietStart=0,quietEnd=0))
        response=client.post('/api/sdk/events',json=dict(events=[event()],reviewRequested=True))
        assert response.status_code==202
        evidence_id=response.json()['receipts'][0]['id']
        client.portal.call(app.state.ingest.step,now+12)
        p.answers=iter([tool('read_proactive_context',{}),dict(role='assistant',content=json.dumps(dict(
            valueScore=85,title='门铃事件有待核对',body='已导入图片里有包裹，可查看这条记录。',reason='摄像头事件提供新观察',sourceIds=['evidence:'+evidence_id])))])
        client.portal.call(app.state.proactive.step,now+13)
        snapshot=client.get('/api/personal').json()
        assert len(snapshot['messages'])==1
        assert snapshot['messages'][0]['sources'][0]['evidenceId']==evidence_id
        assert snapshot['messages'][0]['skillId'] is None
        evidence=app.state.store.evidence()[0]
        assert client.get(evidence['imageUrl']).status_code==200
        assert app.state.visual_review.provider.describe_observations.await_count==1
        assert app.state.store.skills()==[]


def test_unselected_images_never_claim_to_have_been_reviewed(tmp_path):
    async def check():
        s,p,v,i=environment(tmp_path); now=time.time(); at=int(now//10)*10-20
        i.accept(SDKBatch.model_validate(dict(events=[event(str(n),at+n) for n in range(5)],reviewRequested=True)),'client',now)
        await i.step(now+11)
        ep=i.status()['episodes'][0]
        assert len(ep['reviewedEvidenceIds'])==3
        unread=[e for e in s.evidence() if e['id'] not in ep['reviewedEvidenceIds']]
        assert len(unread)==2 and all('未完成视觉核验' in e['reason'] for e in unread)
        assert {x['evidenceId'] for x in i.sources(ep['id']) if x['type']=='camera_evidence'}==set(ep['reviewedEvidenceIds'])
        s.close()
    asyncio.run(check())
