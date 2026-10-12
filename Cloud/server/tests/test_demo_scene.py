import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from evidenceguard.app import create_app
from evidenceguard.demo_scene import DemoScenes, SceneRequest
from evidenceguard.personal import PersonalAgent, Preferences
from evidenceguard.proactive import ProactiveEngine, Decision
from evidenceguard.store import Store
from evidenceguard.visual_review import VisualReview


def environment(tmp_path, monkeypatch):
    monkeypatch.setenv('EG_ENABLE_SYNTHETIC_DEMO','1')
    store=Store(tmp_path/'demo.sqlite')
    vision=SimpleNamespace(ready=True,model='test',base='test',describe_observations=AsyncMock(return_value=dict(visible='前一张有纸箱，后两张区域可见而没有纸箱',uncertainties='只有离散样本，无法确认拿走动作')))
    personal=PersonalAgent(store)
    runtime=SimpleNamespace(proactive=AsyncMock())
    engine=ProactiveEngine(personal,runtime)
    demo=DemoScenes(store,VisualReview(store,vision),engine); engine.demo=demo
    client=str(uuid4()); engine.bind(client,'chat-test')
    personal.preferences(client,Preferences(enabled=True,quietStart=0,quietEnd=0))
    return store,vision,personal,runtime,engine,demo,client


def test_scene_is_opt_in_authenticated_and_does_not_import_sdk(tmp_path,monkeypatch):
    monkeypatch.setenv('EG_ACCESS_TOKEN','x'*40)
    monkeypatch.delenv('EG_ENABLE_SYNTHETIC_DEMO',raising=False)
    app=create_app(tmp_path/'api.sqlite',start_worker=False)
    with TestClient(app) as c:
        body=dict(requestId='test',scenario='parcel_absent')
        assert c.post('/api/demo/scenes',json=body).status_code==401
        c.headers.update({'Authorization':'Bearer '+'x'*40,'X-EG-Installation-ID':str(uuid4())})
        assert c.get('/api/demo/scenes').json()['enabled'] is False
        assert c.post('/api/demo/scenes',json=body).status_code==404
        assert app.state.store.skills()==[] and app.state.ingest.events()==[]


def test_real_review_precedes_policy_and_request_retry_is_idempotent(tmp_path,monkeypatch):
    async def check():
        s,v,p,r,e,d,c=environment(tmp_path,monkeypatch)
        request=SceneRequest(requestId='same',scenario='parcel_absent')
        scene=d.start(c,request); assert d.start(c,request)['id']==scene['id']
        assert len(s.evidence())==3 and e.messages(c)==[]
        with pytest.raises(ValueError): d.start(c,SceneRequest(requestId='other',scenario='unchanged'))
        await d.step()
        assert v.describe_observations.await_count==1
        frames=v.describe_observations.await_args.args[0]
        assert len(frames)==3 and [x[2] for x in frames]==[0,3,6]
        assert all(x['sourceType']=='synthetic_demo' and x['relation']=='unknown' and not x['skillId'] for x in s.evidence())
        r.proactive.return_value=Decision(valueScore=88,reason='明确关注目标有变化，需要查看证据',title='核对测试包裹',body='所给图片中纸箱不再可见，请核对证据。',sourceIds=['evidence:'+scene['samples'][1]['id']])
        await e.step()
        message=e.messages(c)[0]
        assert message['role']=='assistant' and message['sources'][0]['sourceType']=='synthetic_demo'
        assert '测试' in message['body']
        assert d.snapshot(c)['scenes'][0]['policyStatus']=='sent'
        assert d.snapshot(str(uuid4()))['scenes']==[]
        assert d.start(c,request)['id']==scene['id'] and len(e.messages(c))==1
        assert s.skills()==[] and s.runs('chat-test')==[]
        # Evidence detail -> history chat must work for newly created and older
        # saved scenes, without turning generation time into capture time.
        from evidenceguard.harness.tools import build_tools
        tools=build_tools(s,None,execution_mode='history')
        image=await tools.call('read_stored_image',evidence_id=scene['samples'][0]['id'])
        assert image['status']=='completed' and image['historical']
        assert image['timestampMeaning']=='generated' and image['sourceType']=='synthetic_demo'
        with s.transaction():
            import json
            old=s.db.execute('SELECT payload FROM evidence WHERE id=?',(scene['samples'][0]['id'],)).fetchone()[0]
            old=json.loads(old); old.pop('frameId'); old.pop('timestampMeaning')
            s.db.execute('UPDATE evidence SET payload=? WHERE id=?',(json.dumps(old),old['id']))
        assert (await tools.call('read_stored_image',evidence_id=old['id']))['frameId']==old['id']
        items=(await tools.call('search_evidence'))['items']
        assert all('生成时间' in x['timeMeaning'] for x in items)
        s.close()
    asyncio.run(check())


def test_daily_digest_keeps_original_review_and_playable_evidence(tmp_path,monkeypatch):
    async def check():
        from evidenceguard.proactive import Decision
        import time
        s,v,p,r,e,d,c=environment(tmp_path,monkeypatch)
        p.preferences(c,Preferences(enabled=True,dailySummary=True,quietStart=0,quietEnd=0))
        scene=d.start(c,SceneRequest(requestId='digest',scenario='parcel_absent'))
        await d.step()
        source_id='evidence:'+scene['samples'][1]['id']
        r.proactive.return_value=Decision(valueScore=60,reason='测试变化，适合汇总',title='测试变化',body='合成样本中纸箱不再可见。',sourceIds=[source_id])
        await e.step()
        assert e.activity(c)[0]['status']=='digest' and e.messages(c)==[]
        r.proactive.return_value=Decision(valueScore=60,reason='已订阅测试汇总',title='测试汇总',body='合成样本有变化，无法确认真实拿走动作。',sourceIds=['digest:'+e.activity(c)[0]['id'],source_id])
        e.enqueue(c,'daily','schedule','概况','订阅的每日概况',time.time())
        await e.step()
        context=r.proactive.await_args.args[1]
        original=next(x for x in context['sources'] if x['id']==source_id)
        assert original['visualReview']['status']=='completed'
        assert original['sourceType']=='synthetic_demo' and original['imageUrl']
        assert v.describe_observations.await_count==1  # Reuse, no second vision call.
        message=e.messages(c)[0]
        assert any(x['id']==source_id and x['imageUrl'] for x in message['sources'])
        assert '测试' in message['body'] and message['kind']=='schedule'
        assert e.activity(c)[1]['status']=='summarized'
        assert e.messages(str(uuid4()))==[]
        s.close()
    asyncio.run(check())


@pytest.mark.parametrize('result',['failed','quiet','low_score','disabled'])
def test_failed_unknown_and_policy_suppression_never_force_success(tmp_path,monkeypatch,result):
    async def check():
        s,v,p,r,e,d,c=environment(tmp_path,monkeypatch)
        if result=='failed': v.describe_observations.side_effect=RuntimeError('secret must not be disclosed')
        if result=='disabled': p.preferences(c,Preferences(enabled=False))
        if result=='quiet':
            hour=datetime.now(timezone.utc).hour
            p.preferences(c,Preferences(enabled=True,quietStart=hour,quietEnd=(hour+1)%24))
        scene=d.start(c,SceneRequest(requestId='one',scenario='occluded' if result=='failed' else 'unchanged'))
        await d.step()
        r.proactive.return_value=Decision(valueScore=20,reason='样本未显示需要用户处理的新信息')
        await e.step()
        assert e.messages(c)==[] and s.skills()==[]
        item=d.snapshot(c)['scenes'][0]
        if result=='failed': assert item['status']=='unavailable' and 'secret' not in str(item)
        elif result=='quiet': assert item['policyStatus']=='deferred'; r.proactive.assert_not_awaited()
        elif result=='low_score': assert item['policyStatus']=='silent'
        else: assert item['policyStatus'] is None; r.proactive.assert_not_awaited()
        s.close()
    asyncio.run(check())
