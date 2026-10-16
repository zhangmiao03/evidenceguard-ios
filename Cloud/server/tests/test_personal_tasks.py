import asyncio
import time
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from evidenceguard.app import create_app
from evidenceguard.personal import PersonalAgent, Preferences
from evidenceguard.store import Store
from evidenceguard.camera.ingest import SDKBatch, SDKDevices, SDKDevice
from test_harness import ScriptedProvider, tool, settle
from test_sdk_ingest import event


def request(client, key='request'):
    return dict(id=key,clientId=client,executionMode='live',conversationId='chat-'+client,message='今天有快递来了提醒我')


def test_task_persists_idempotently_expires_at_local_midnight_and_is_isolated(tmp_path):
    path=tmp_path/'tasks.sqlite'; s=Store(path); p=PersonalAgent(s)
    now=datetime(2026,10,16,16,30,tzinfo=ZoneInfo('Asia/Shanghai')).timestamp()
    a,b=str(uuid4()),str(uuid4())
    t=p.tasks.create(a,request(a),'关注快递','package_put','sdk-a','today','Asia/Shanghai',now)
    assert p.tasks.create(a,request(a),'重复请求','motion','sdk-b','ongoing','UTC',now)==t
    assert p.tasks.list(b,now)==[]
    assert datetime.fromtimestamp(t['expiresAt'],ZoneInfo('Asia/Shanghai')).hour==0
    ep=dict(cameraId='sdk-a',kind='package_put')
    assert p.tasks.matching(a,ep,now+1,now+2)==[t]
    assert not p.tasks.matching(a,ep,now-1,now+2)
    assert not p.tasks.matching(a,ep|dict(cameraId='sdk-b'),now+1,now+2)
    assert not p.tasks.matching(a,ep,now+1,t['expiresAt'])
    with pytest.raises(KeyError): p.tasks.cancel(b,t['id'])
    s.close(); s=Store(path); p=PersonalAgent(s)
    assert p.tasks.list(a,now)[0]['id']==t['id']
    p.tasks.cancel(a,t['id']); assert p.tasks.list(a,now)[0]['status']=='cancelled'
    s.close()


def test_conversation_tool_receipt_reaches_task_page_and_history_cannot_write(tmp_path,monkeypatch):
    monkeypatch.setenv('EG_CAMERA_SOURCE','official_sdk')
    async def check():
        p=ScriptedProvider([tool('save_personal_task',dict(title='今天关注快递',event_type='package_put',period='today')),
                            dict(role='assistant',content='已保存，请保持前台事件同步。')])
        app=create_app(tmp_path/'flow.sqlite',start_worker=False,provider=p); a=str(uuid4())
        app.state.ingest.register_devices(SDKDevices(devices=[SDKDevice(deviceSn='T8214-TEST',model='T8214',deviceName='门口')]))
        camera=app.state.ingest.camera_id('T8214-TEST')
        runtime=app.state.agent
        run=await settle(runtime,runtime.start('今天有快递来了提醒我','chat',camera_id=camera,client_id=a,client_platform='iOS'))
        assert run['status']=='completed'
        assert run['toolReceipts']==[dict(tool='save_personal_task',status='completed')]
        assert app.state.personal.snapshot(a)['tasks'][0]['status']=='waiting_events'
        scoped=runtime.tools.for_context(None,camera,'history',run=run)
        assert 'save_personal_task' not in scoped.names
        assert not app.state.store.skills()
        await runtime.scheduler.shutdown(); await app.state.push.provider.close(); await app.state.videos.shutdown(); app.state.store.close()
    asyncio.run(check())


def test_default_events_are_saved_without_alerting_and_explicit_watch_is_scoped(tmp_path):
    app=create_app(tmp_path/'events.sqlite',start_worker=False,provider=ScriptedProvider([]))
    a,b=str(uuid4()),str(uuid4()); now=time.time(); ing=app.state.ingest
    app.state.visual_review.provider=SimpleNamespace(ready=True,model='test',base='test',describe_observations=AsyncMock(return_value=dict(visible='人物',uncertainties='单帧未知动作')))
    with TestClient(app) as client:
        for who in (a,b): app.state.personal.preferences(who,Preferences(enabled=True,quietStart=0,quietEnd=0))
        camera=ing.camera_id('T8214-TEST')
        ing.accept(SDKBatch.model_validate(dict(events=[event('noise',now-1)],reviewRequested=True)),a,now)
        client.portal.call(ing.step,now+11)
        assert len(app.state.store.evidence())==1
        assert app.state.proactive.activity(a)==app.state.proactive.activity(b)==[]
        ep=ing.status()['episodes'][0]
        app.state.proactive.enqueue(a,ep['id'],'camera_event','旧队列','旧队列',now+11)
        client.portal.call(app.state.proactive.step,now+12)
        assert app.state.proactive.activity(a)[0]['status']=='cancelled'
        t=app.state.personal.tasks.create(a,request(a),'有人活动提醒','human',camera,'today','Asia/Shanghai',now-2)
        ing.accept(SDKBatch.model_validate(dict(events=[event('wanted',now-1,detectionType='human')],reviewRequested=True)),a,now)
        client.portal.call(ing.step,now+11); client.portal.call(app.state.proactive.step,now+13)
        assert len(app.state.proactive.messages(a))==1 and not app.state.proactive.messages(b)
        message=app.state.proactive.messages(a)[0]
        assert '人物活动' in message['body'] and any(x.get('cameraId')==camera for x in message['sources'])
        client.headers['X-EG-Installation-ID']=b
        assert client.post('/api/personal/tasks/'+t['id']+'/cancel').status_code==404
        client.headers['X-EG-Installation-ID']=a
        assert client.post('/api/personal/tasks/'+t['id']+'/cancel').json()['tasks'][0]['status']=='cancelled'


def test_unsupported_requests_are_saved_without_claiming_execution(tmp_path):
    s=Store(tmp_path/'pending.sqlite'); p=PersonalAgent(s); a=str(uuid4())
    t=p.tasks.create(a,request(a),'晚上提醒我吃药',None,None,'ongoing','UTC')
    assert t['status']=='needs_setup' and '尚未启用' in t['reason']
    assert not p.tasks.matching(a,dict(cameraId='sdk-a',kind='motion'),time.time(),time.time())
    s.close()
