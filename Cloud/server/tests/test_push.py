import asyncio
import json
import time
from uuid import uuid4
from unittest.mock import AsyncMock

import httpx
import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

from evidenceguard.app import create_app
from evidenceguard.personal import Preferences
from evidenceguard.push import APNsProvider, DeviceRegistration, PushService
from test_proactive import setup, answers


SECRET = 'ab' * 32
TOKEN = 'cd' * 32


class Provider:
    ready = True
    environment = 'production'
    topic = 'com.zhangmiao.evidenceguard'
    def __init__(self): self.send = AsyncMock(return_value=(200,''))
    async def close(self): pass


def registration(token=TOKEN):
    return DeviceRegistration(token=token,environment='production',topic=Provider.topic)


def fixture(tmp_path, monkeypatch):
    p,s,r,personal,e,c,skill = setup(tmp_path)
    monkeypatch.setenv('EG_PUSH_SCOPE','demo')
    push = PushService(s,personal,Provider()); e.push=push; r.push=push
    push.register(c,SECRET,registration())
    return p,s,r,personal,e,c,skill,push


def test_proactive_publication_atomic_dedupe_and_open(tmp_path, monkeypatch):
    async def check():
        p,s,r,personal,e,c,skill,push=fixture(tmp_path,monkeypatch)
        answers(p,skill); personal.tick(); await e.step()
        msg=e.messages(c)[0]
        row=s.db.execute('SELECT id FROM push_outbox').fetchone(); assert row
        key=row[0]
        assert push.enqueue(c,msg['id'],'message',{'messageId':msg['id']})==key
        assert await push.step()
        assert push.status(c,SECRET)['lastState']=='accepted'
        assert push.status(c,SECRET)['openedAt'] is None
        assert not await push.step()
        target=push.open(c,SECRET,key)
        assert target['skillId']==skill['id'] and target['messageId']==msg['id']
        assert push.status(c,SECRET)['openedAt'] is not None and e.messages(c)[0]['read']
        assert push.provider.send.await_count==1
        s.close()
    asyncio.run(check())


@pytest.mark.parametrize('change',['read','disabled','resolved','quiet','new_episode','snooze'])
def test_pending_rechecks_user_and_event_state(tmp_path,monkeypatch,change):
    async def check():
        p,s,r,personal,e,c,skill,push=fixture(tmp_path,monkeypatch)
        answers(p,skill); personal.tick(); await e.step()
        msg=e.messages(c)[0]
        if change=='read': personal.read(c,msg['id'])
        if change=='disabled': push.disable(c,SECRET)
        if change=='resolved': skill['alert']='none'; s.save_skill(skill)
        if change=='quiet':
            from datetime import datetime
            hour=datetime.now().hour
            personal.preferences(c,Preferences(enabled=True,timezone='Asia/Shanghai',quietStart=hour,quietEnd=(hour+1)%24))
            # Use UTC explicitly to keep the test independent of the test host TZ.
            from datetime import timezone
            hour=datetime.now(timezone.utc).hour
            personal.preferences(c,Preferences(enabled=True,quietStart=hour,quietEnd=(hour+1)%24))
        if change=='new_episode': s.event(skill['id'],'alert_opened',{})
        if change=='snooze': e.feedback(c,msg['id'],'snooze')
        await push.step()
        push.provider.send.assert_not_awaited()
        assert push.status(c,SECRET)['lastState']==('retry' if change=='quiet' else 'cancelled')
        s.close()
    asyncio.run(check())


def test_retry_restart_stable_id_and_expiry(tmp_path,monkeypatch):
    async def check():
        p,s,r,personal,e,c,skill,push=fixture(tmp_path,monkeypatch)
        now=time.time(); key=push.enqueue(c,'test:one','test',{},now)
        push.provider.send.return_value=(503,'Shutdown')
        await push.step(now)
        item=push.row(key); assert item['state']=='retry' and item['due']>=now+900
        await push.step(now+899); assert push.provider.send.await_count==1
        recovered=PushService(s,personal,Provider())
        await recovered.step(now+901)
        assert recovered.row(key)['state']=='accepted'
        assert recovered.provider.send.call_args.args[1]['id']==key
        expired=push.enqueue(c,'test:two','test',{},now,expires=now+10)
        await push.step(now+11)
        assert push.row(expired)['state']=='expired'
        s.close()
    asyncio.run(check())


@pytest.mark.parametrize('rotate',[False,True])
def test_invalid_token_only_disables_the_rejected_registration(tmp_path,monkeypatch,rotate):
    async def check():
        *_,c,skill,push=fixture(tmp_path,monkeypatch)
        async def reject(*args):
            if rotate: push.register(c,SECRET,registration('ef'*32))
            return 410,'Unregistered'
        push.provider.send.side_effect=reject
        key=push.enqueue(c,'test:invalid','test',{})
        await push.step()
        assert push.row(key)['state']=='failed'
        assert bool(push.device(c)['enabled'])==rotate
        push.store.close()
    asyncio.run(check())


def test_registration_identity_scope_and_disable(tmp_path,monkeypatch):
    *_,c,skill,push=fixture(tmp_path,monkeypatch)
    for action in [lambda:push.register(c,'ff'*32,registration()),lambda:push.disable(c,'ff'*32),lambda:push.status(c,'ff'*32)]:
        with pytest.raises(HTTPException) as error: action()
        assert error.value.status_code==403
    with pytest.raises(HTTPException): push.register(str(uuid4()),SECRET,registration())
    with pytest.raises(HTTPException): push.register(c,SECRET,DeviceRegistration(token=TOKEN,environment='development',topic=Provider.topic))
    with pytest.raises(HTTPException): push.register(c,SECRET,DeviceRegistration(token=TOKEN,environment='production',topic='another.bundle'))
    assert TOKEN not in json.dumps(push.status(c,SECRET)) and SECRET not in json.dumps(push.status(c,SECRET))
    key=push.enqueue(c,'test:cancel','test',{})
    push.disable(c,SECRET)
    assert push.device(c)['token']!=TOKEN and push.row(key)['state']=='cancelled'
    assert push.enqueue(c,'test:no','test',{}) is None
    push.store.close()


def test_api_requires_bearer_and_device_secret_and_does_not_cross_services(tmp_path,monkeypatch):
    bearer='team-'+'x'*40
    monkeypatch.setenv('EG_ACCESS_TOKEN',bearer);monkeypatch.setenv('EG_REQUIRE_AUTH','1')
    monkeypatch.setenv('EG_PUSH_SCOPE','demo')
    app=create_app(tmp_path/'demo.sqlite',start_worker=False)
    with TestClient(app,base_url='https://testserver') as http:
        client=str(uuid4()); headers={'Authorization':'Bearer '+bearer,'X-EG-Installation-ID':client,'X-EG-Push-Key':SECRET}
        assert http.get('/api/push/status').status_code==401
        assert http.get('/api/push/status',headers={'Authorization':'Bearer '+bearer,'X-EG-Installation-ID':client}).status_code==403
        assert http.put('/api/push/device',headers=headers,json=registration().model_dump()).status_code==200
        app.state.push.provider=Provider()
        response=http.post('/api/push/test',headers=headers); assert response.status_code==202
        key=response.json()['id']
        assert http.post('/api/push/test',headers=headers).status_code==429
        other=str(uuid4()); other_headers=headers|{'X-EG-Installation-ID':other}
        http.put('/api/push/device',headers=other_headers,json=registration('ef'*32).model_dump())
        assert http.post('/api/push/deliveries/'+key+'/open',headers=other_headers).status_code==404
        assert http.post('/api/push/deliveries/'+key+'/open',headers=headers).json()['kind']=='test'
        assert http.put('/api/push/device',headers=headers,json=registration().model_dump()|{'token':'not hex'}).status_code==422
    monkeypatch.setenv('EG_PUSH_SCOPE','review')
    second=create_app(tmp_path/'review.sqlite',start_worker=False)
    with TestClient(second,base_url='https://testserver') as http:
        status=http.get('/api/push/status',headers=headers).json()
        assert status['scope']=='review' and not status['registered']
        assert http.post('/api/push/deliveries/'+key+'/open',headers=headers).status_code==404


@pytest.mark.parametrize('kind,body', [
    ('test','这是一条测试提醒，点开后可以查看结果。'),
    ('run','这件事有结果了，点开看看。'),
    ('draft','草案整理好了，等你看看。'),
    ('message','有件事想提醒你，点开看看。'),
])
def test_provider_http2_payload_is_generic_and_jwt_cached(tmp_path,monkeypatch,kind,body):
    async def check():
        key=ec.generate_private_key(ec.SECP256R1()); path=tmp_path/'apns.p8'
        path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        for k,v in {'EG_APNS_ENABLED':'1','EG_APNS_TEAM_ID':'TESTTEAM','EG_APNS_KEY_ID':'TESTKEY','EG_APNS_KEY_PATH':str(path)}.items(): monkeypatch.setenv(k,v)
        provider=APNsProvider(); assert provider.ready
        authorization=provider.authorization();assert authorization==provider.authorization()
        claims=jwt.decode(authorization[7:],key.public_key(),algorithms=['ES256'],options={'verify_iat':False})
        assert claims['iss']=='TESTTEAM'
        def respond(request):
            assert request.url.host=='api.push.apple.com'
            assert request.headers['apns-topic']==Provider.topic
            assert request.headers['apns-push-type']=='alert'
            payload=json.loads(request.content)
            assert set(payload['eg'])=={'deliveryId','scope'}
            assert payload['aps']['alert']=={'title':'anker','body':body}
            assert payload['aps']['thread-id']=='evidenceguard-demo'
            assert 'private message' not in request.content.decode()
            return httpx.Response(200)
        provider.clients['production']=httpx.AsyncClient(transport=httpx.MockTransport(respond))
        assert await provider.send({'environment':'production','token':TOKEN},{'id':str(uuid4()),'kind':kind,'expires_at':time.time()+300,'private':'private message'},'demo')==(200,'')
        await provider.close()
    asyncio.run(check())


def test_foreground_lease_and_push_frequency_limit(tmp_path,monkeypatch):
    async def check():
        *_,c,skill,push=fixture(tmp_path,monkeypatch)
        now=time.time();push.presence(c,SECRET,True)
        key=push.enqueue(c,'run:one','run',{'runId':'r'},now)
        await push.step(now); assert push.row(key)['reason']=='AppVisible'
        await push.step(now+80); assert push.row(key)['state']=='accepted'
        next_key=push.enqueue(c,'run:two','run',{'runId':'r2'},now+81)
        await push.step(now+81); assert push.row(next_key)['reason']=='RateLimit'
        push.store.close()
    asyncio.run(check())


def test_run_result_and_outbox_commit_together(tmp_path,monkeypatch):
    async def check():
        p,s,r,personal,e,c,skill,push=fixture(tmp_path,monkeypatch)
        p.complete=AsyncMock(return_value={'role':'assistant','content':'查询完成'})
        run=r.start('看一下历史结果','history-chat',execution_mode='history')
        run['clientId']=c
        await asyncio.gather(*r.tasks.values())
        assert s.run(run['id'])['status']=='completed'
        row=s.db.execute('SELECT id FROM push_outbox').fetchone()
        assert row
        target=push.open(c,SECRET,row[0])
        assert target['conversationId']=='history-chat' and target['executionMode']=='history'
        s.close()
    asyncio.run(check())
