import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
import pytest
from evidenceguard.app import create_app
from evidenceguard.camera.watch import WatchOptions
from evidenceguard.camera.ingest import SDKBatch
from evidenceguard.personal import Preferences
from evidenceguard.push import PushService
from test_harness import ScriptedProvider, tool
from test_push import Provider, SECRET, registration
from test_sdk_ingest import event


def setup(tmp_path):
    provider=ScriptedProvider([])
    app=create_app(tmp_path/'watch.sqlite',provider=provider,start_worker=False)
    s=app.state.store; w=app.state.watch
    cameras=[SimpleNamespace(id='first',name='门口',connection='online'),SimpleNamespace(id='second',name='后院',connection='online')]
    w.captures=SimpleNamespace(cameras=SimpleNamespace(manifests=AsyncMock(return_value=cameras)),capture=AsyncMock())
    w.visual=SimpleNamespace(review=AsyncMock(return_value=dict(status='completed',review=dict(visible='图中有人',uncertainties='无法确认身份或持续状态'))),usage=lambda _:dict(requests=0,limit=100))
    owner=str(uuid4()); p=app.state.personal
    p.preferences(owner,Preferences(enabled=True,quietStart=0,quietEnd=0))
    app.state.proactive.bind(owner,'chat')
    return app,provider,s,w,owner


def receipt(source='official_live_ios',age=1):
    return dict(status='completed',frameId='frame',imageUrl='/api/media/'+'a'*64,mediaId='a'*64,
                sourceType=source,sampledAt=time.time()-age,capturedAt=None,timestampMeaning='client_live_sample')


def test_two_camera_schedules_persist_separately_and_feed_proactive_push_once(tmp_path,monkeypatch):
    async def check():
        app,p,s,w,owner=setup(tmp_path)
        w.captures.capture.return_value=receipt()
        await w.configure('first',WatchOptions(enabled=True)); await w.configure('second',WatchOptions(enabled=True,intervalSeconds=3600))
        assert await w.step() and await w.step() and not await w.step()
        assert {c.args[0] for c in w.captures.capture.await_args_list}=={'first','second'}
        assert w.visual.review.await_count==2
        rows=s.db.execute('SELECT payload FROM camera_observations ORDER BY rowid').fetchall()
        observations=[json.loads(r[0]) for r in rows]
        assert len(observations)==2 and len(s.evidence())==2 and s.skills()==[]
        observation=observations[0]
        p.answers=iter([tool('read_proactive_context',{}),dict(role='assistant',content=json.dumps(dict(valueScore=85,title='门口有个新动态',body='刚收到的一张画面里有人，可以看一下。',reason='用户开启的定时取样发现人员',sourceIds=['evidence:'+observation['id']]),ensure_ascii=False))])
        monkeypatch.setenv('EG_PUSH_SCOPE','test')
        push=PushService(s,app.state.personal,Provider()); app.state.proactive.push=push
        push.register(owner,SECRET,registration())
        await app.state.proactive.step()
        messages=app.state.proactive.messages(owner)
        assert len(messages)==1 and messages[0]['sources'][0]['evidenceId']==observation['id']
        assert len(s.db.execute('SELECT id FROM push_outbox').fetchall())==1
        assert await push.step() and not await push.step()
        assert push.provider.send.await_count==1
        assert push.status(owner,SECRET)['lastState']=='accepted'
        # Accepted by a fake APNs provider is deliberately not device delivery.
        assert push.status(owner,SECRET)['openedAt'] is None
        from evidenceguard.camera.watch import CameraWatch
        restarted=CameraWatch(s,w.captures,w.visual,app.state.proactive)
        assert len(await restarted.snapshot())==2 and not await restarted.step()
        s.close()
    asyncio.run(check())


@pytest.mark.parametrize('mode',['offline','fixture','stale','future','busy','model_budget','disabled_during_review'])
def test_no_fabricated_observation_or_notice_when_capture_is_unusable(tmp_path,mode):
    async def check():
        app,p,s,w,owner=setup(tmp_path)
        await w.configure('first',WatchOptions(enabled=True))
        value=receipt()
        if mode=='offline': value=dict(status='offline',reason='采集端离线')
        if mode=='fixture': value=receipt(source='fixture_lab')
        if mode=='stale': value=receipt(age=1000)
        if mode=='future': value=receipt(age=-100)
        if mode=='busy': w.captures.capture.side_effect=ValueError('occupied')
        w.captures.capture.return_value=value
        if mode=='model_budget': w.visual.review.return_value=dict(status='budget_exhausted',reason='额度已用完')
        if mode=='disabled_during_review':
            async def disable(*args):
                await w.configure('first',WatchOptions(enabled=False))
                return dict(status='completed',review={'visible':'有人'})
            w.visual.review.side_effect=disable
        await w.step()
        assert s.db.execute('SELECT COUNT(*) FROM camera_observations').fetchone()[0]==0
        assert s.db.execute('SELECT COUNT(*) FROM proactive_jobs').fetchone()[0]==0
        assert s.evidence()==[]
        assert w.get('first')['status']!='completed'
        if mode in {'offline','fixture','stale','future','busy'}: w.visual.review.assert_not_awaited()
        s.close()
    asyncio.run(check())


def test_schedule_pause_and_stale_observation_revalidate_before_sending(tmp_path):
    async def check():
        app,p,s,w,owner=setup(tmp_path); w.captures.capture.return_value=receipt()
        await w.configure('first',WatchOptions(enabled=True)); await w.step()
        await w.configure('first',WatchOptions(enabled=False)); await app.state.proactive.step()
        assert app.state.proactive.messages(owner)==[] and app.state.proactive.activity(owner)[0]['status']=='cancelled'
        p.complete.assert_not_awaited()
        s.close()
    asyncio.run(check())


@pytest.mark.parametrize('kind',['human','ring'])
def test_fresh_device_event_without_image_can_notify_with_explicit_metadata_boundary(tmp_path,kind):
    async def check():
        app,p,s,w,owner=setup(tmp_path); now=time.time()
        app.state.personal.tasks.create(owner,dict(id='watch-request',clientId=owner,executionMode='live',conversationId='watch',message='有新事件提醒我'),
            '设备事件关注',kind,app.state.ingest.camera_id('T8214-TEST'),'today','Asia/Shanghai',now-60)
        app.state.ingest.accept(SDKBatch.model_validate(dict(events=[event(image=False,detectionType=kind)],reviewRequested=True)),owner,now)
        await app.state.ingest.step(now+11)
        ep=app.state.ingest.status()['episodes'][0]
        assert ep['status']=='metadata_only'
        sources=app.state.ingest.sources(ep['id'])
        assert len(sources)==2 and sources[0]['type']=='task_state' and '尚无可核验图片' in sources[0]['reason']
        p.answers=iter([tool('read_proactive_context',{}),dict(role='assistant',content=json.dumps(dict(valueScore=85,title='门口有设备事件',body='设备报告了新事件，还没有可核验图片，你可以打开查看。',reason='新设备事件',sourceIds=[ep['id']]),ensure_ascii=False))])
        await app.state.proactive.step(now+12)
        assert len(app.state.proactive.messages(owner))==1
        assert app.state.proactive.messages(owner)[0]['sources'][0].get('imageUrl') is None
        await app.state.ingest.step(now+13)
        assert len(app.state.proactive.messages(owner))==1
        s.close()
    asyncio.run(check())
