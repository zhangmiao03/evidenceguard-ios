import asyncio
import base64
import io
import json
import time

import httpx
import pytest
from unittest.mock import AsyncMock
from PIL import Image
from fastapi.testclient import TestClient

from evidenceguard.app import create_app
from evidenceguard.camera.live import DeviceImport, SessionStart, Heartbeat, FrameUpload
from evidenceguard.camera.contracts import CameraCommandContext, SnapshotKind


def imported(hub, client='phone', sn='T8171TEST0001'):
    return hub.import_devices(DeviceImport(accountId='official-user', platform='ios',
        devices=[dict(sn=sn, model=sn[:5], name='客厅')]), client)[0]


def ready(hub, device_id, client='phone'):
    receipt = hub.start(SessionStart(deviceId=device_id, platform='ios'), client)
    s = hub.authorize(receipt['id'], client, receipt['token'])
    hub.heartbeat(s, Heartbeat(state='streaming', sequence=1, frameAgeMs=0))
    return receipt, s


def picture(request, sequence=2):
    f = io.BytesIO()
    Image.new('RGB', (32, 24), (80, 90, 120)).save(f, format='JPEG')
    return dict(requestId=request, sequence=sequence, width=32, height=24,
                imageBase64=base64.b64encode(f.getvalue()).decode(), sampledAt=time.time())


def test_event_and_live_discovery_share_one_camera_without_stale_live_claims(tmp_path, monkeypatch):
    from test_sdk_ingest import event
    monkeypatch.setenv('EG_CAMERA_SOURCE', 'official_sdk')
    app = create_app(tmp_path/'unified.sqlite', start_worker=False)
    with TestClient(app) as client:
        from uuid import uuid4
        client.headers['X-EG-Installation-ID'] = str(uuid4())
        hub = app.state.camera.live
        d = imported(hub, sn='T8214TEST0001')
        assert client.post('/api/sdk/events', json={'events': [event(deviceSn=d['sn'])]}).status_code == 202
        cameras = client.get('/api/bootstrap').json()['cameras']
        assert len(cameras) == 1 and cameras[0]['id'] == d['id']
        assert cameras[0]['capabilities']['storedSnapshot'] == 'supported'
        assert cameras[0]['capabilities']['liveSnapshot'] == 'unknown'
        thumbnail = cameras[0]['lastFrameUrl']
        _, session = ready(hub, d['id'])
        live = client.get('/api/bootstrap').json()['cameras'][0]
        assert live['connection'] == 'online' and live['capabilities']['liveSnapshot'] == 'supported'
        assert live['lastCapturedAt'] is None
        hub.stop(session)
        offline = client.get('/api/bootstrap').json()['cameras'][0]
        assert offline['capabilities']['liveSnapshot'] == 'unknown'
        assert offline['lastFrameUrl'] == thumbnail  # History stays visible, never becomes a fresh capture.
        assert len(client.portal.call(app.state.camera.state)['cameras']) == 1


def test_live_only_device_does_not_trigger_no_camera_reply(tmp_path, monkeypatch):
    from test_harness import ScriptedProvider, tool, settle
    monkeypatch.setenv('EG_CAMERA_MODE', 'official')
    provider = ScriptedProvider([tool('list_camera_events', {}), dict(role='assistant', content='这台设备还没有同步事件记录。')])
    app = create_app(tmp_path/'live-only.sqlite', start_worker=False, provider=provider)
    with TestClient(app) as client:
        d = imported(app.state.camera.live)
        result = client.portal.call(lambda: app.state.tools.call('list_camera_events'))
        assert result['registeredDeviceCount'] == 1 and result['count'] == 0
        assert 'nextStep' not in result
        run = client.portal.call(lambda: settle(app.state.agent, app.state.agent.start('摄像头最近发生什么？', 'live-events', camera_id=d['id'])))
        assert run['status'] == 'completed' and run['text'] == '这台设备还没有同步事件记录。'
        assert app.state.store.skills() == []


def test_device_identity_and_account_conflicts_are_durable(tmp_path):
    path = tmp_path/'db.sqlite3'
    app = create_app(path, start_worker=False)
    hub = app.state.camera.live
    d = imported(hub)
    assert imported(hub)['id'] == d['id']
    assert imported(hub, sn='T8171TEST0002')['id'] != d['id']
    with pytest.raises(ValueError, match='账号'):
        hub.import_devices(DeviceImport(accountId='other', platform='web', devices=[dict(sn=d['sn'], model=d['model'], name='其他')]), 'browser')
    ready(hub, d['id'])
    other = create_app(path, start_worker=False)
    assert len(other.state.camera.live.records()) == 2
    assert other.state.camera.live.current(d['id']) is None
    app.state.store.close()
    other.state.store.close()


def test_agent_capture_requires_a_new_frame_for_the_correct_session(tmp_path):
    async def run():
        app = create_app(tmp_path/'db.sqlite3', start_worker=False)
        hub = app.state.camera.live
        d = imported(hub)
        _, s = ready(hub, d['id'])
        capture = asyncio.create_task(app.state.tools.call('request_camera_snapshot', device_id=d['id']))
        # App exposes tools through its Agent runtime rather than a second implementation.
        for _ in range(50):
            commands = hub.commands(s)
            if commands: break
            await asyncio.sleep(.01)
        request = commands[0]['requestId']
        with pytest.raises(ValueError, match='新直播'):
            hub.upload(s, FrameUpload(**picture(request, 1)))
        d2 = imported(hub, sn='T8214TEST0001')
        _, s2 = ready(hub, d2['id'], 'second')
        with pytest.raises(ValueError, match='匹配'):
            hub.upload(s2, FrameUpload(**picture(request)))
        hub.upload(s, FrameUpload(**picture(request)))
        result = await capture
        assert result['status'] == 'completed'
        assert result['cameraId'] == d['id']
        assert result['capturedAt'] is None
        assert result['timestampMeaning'] == 'client_live_sample'
        assert app.state.store.media(result['mediaId'])[1] == 'image/jpeg'
        assert not hub.pending
        with pytest.raises(ValueError, match='匹配'):
            hub.upload(s, FrameUpload(**picture(request)))
        await app.state.agent.shutdown()
        app.state.store.close()
    asyncio.run(run())


def test_capture_cancel_stop_and_stale_input_do_not_report_success(tmp_path):
    async def run():
        app = create_app(tmp_path/'db.sqlite3', start_worker=False)
        hub = app.state.camera.live
        d = imported(hub)
        _, s = ready(hub, d['id'])
        context = CameraCommandContext('one', 'owner', 'epoch', time.time()+5)
        task = asyncio.create_task(hub.snapshot(d['id'], SnapshotKind.LIVE, context))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert not hub.pending
        with pytest.raises(ValueError): hub.upload(s, FrameUpload(**picture('one')))
        task = asyncio.create_task(hub.snapshot(d['id'], SnapshotKind.LIVE, context))
        await asyncio.sleep(0)
        hub.stop(s)
        with pytest.raises(ValueError, match='停止'): await task
        _, s = ready(hub, d['id'])
        s['heartbeatAt'] -= 20
        manifests = await hub.manifests()
        assert manifests[0].connection != 'online'
        with pytest.raises(ValueError, match='活跃'): await hub.snapshot(d['id'], SnapshotKind.LIVE, context)
        app.state.store.close()
    asyncio.run(run())


def test_routes_session_auth_and_public_web_shell(tmp_path, monkeypatch):
    monkeypatch.setenv('EG_ACCESS_TOKEN', 'a'*40)
    web = tmp_path/'web'
    web.mkdir()
    (web/'index.html').write_text('<html>EvidenceGuard</html>')
    monkeypatch.setenv('EG_WEB_ROOT', str(web))
    app = create_app(tmp_path/'db.sqlite3', start_worker=False)
    headers = {'Authorization':'Bearer '+'a'*40, 'X-EG-Installation-ID':'00000000-0000-4000-8000-000000000001'}
    with TestClient(app) as client:
        assert client.get('/').status_code == 200
        assert client.get('/docs').status_code == 401
        assert client.get('/api/devices').status_code == 401
        d = client.post('/api/devices/import', headers=headers, json=dict(accountId='u', platform='ios', devices=[dict(sn='T8171TEST0001', model='T8171', name='客厅')])).json()[0]
        s = client.post('/api/media-sessions', headers=headers, json=dict(deviceId=d['id'], platform='ios')).json()
        url = '/api/media-sessions/'+s['id']
        assert client.get(url+'/commands', headers=headers).status_code == 404
        headers['X-EG-Media-Session'] = s['token']
        assert client.get(url+'/commands', headers=headers).json() == []
        wrong = headers | {'X-EG-Installation-ID':'00000000-0000-4000-8000-000000000002'}
        assert client.get(url+'/commands', headers=wrong).status_code == 404
        assert client.post(url+'/frames', headers=headers, content=b'not JSON').status_code == 422
        assert client.post(url+'/stop', headers=headers).json()['status'] == 'stopped'
        assert client.get(url+'/commands', headers=headers).status_code == 409
        assert client.post('/api/sdk/openapi/v1/x', headers={'Authorization':'Bearer vendor-token'}).status_code == 401


def test_http_capture_exchange(tmp_path):
    async def run():
        app = create_app(tmp_path/'db.sqlite3', start_worker=False)
        headers = {'X-EG-Installation-ID':'00000000-0000-4000-8000-000000000001'}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers=headers) as client:
            d = (await client.post('/api/devices/import', json=dict(accountId='u', platform='web', devices=[dict(sn='T8214TEST0001', model='T8214', name='门口')]))).json()[0]
            s = (await client.post('/api/media-sessions', json=dict(deviceId=d['id'], platform='web'))).json()
            client.headers['X-EG-Media-Session'] = s['token']
            url = '/api/media-sessions/'+s['id']
            await client.post(url+'/heartbeat', json=dict(state='streaming', sequence=1, frameAgeMs=0))
            task = asyncio.create_task(client.post('/api/devices/'+d['id']+'/capture', json={}))
            for _ in range(50):
                commands = (await client.get(url+'/commands')).json()
                if commands: break
                await asyncio.sleep(.01)
            bad = picture(commands[0]['requestId']) | {'width': 50}
            assert (await client.post(url+'/frames', json=bad)).status_code == 409
            assert (await client.post(url+'/frames', json=picture(commands[0]['requestId']))).status_code == 200
            assert (await task).json()['status'] == 'completed'
            records = (await client.get('/api/captures')).json()
            assert len(records) == 1 and records[0]['cameraId'] == d['id']
            assert records[0]['deviceName'] == '门口' and records[0]['capturedAt'] is None
            assert (await client.get(records[0]['imageUrl'])).headers['content-type'] == 'image/jpeg'
            assert (await client.get('/api/bootstrap')).json()['cameras'][0]['id'] == d['id']
        await app.state.agent.shutdown()
        app.state.store.close()
    asyncio.run(run())


def test_push_binding_and_live_lease_remain_independent(tmp_path, monkeypatch):
    monkeypatch.setenv('EG_ACCESS_TOKEN', 'a' * 40)
    monkeypatch.setenv('EG_APNS_ENABLED', '0')
    monkeypatch.setenv('EG_APNS_TOPIC', 'com.evidenceguard.integration')
    monkeypatch.setenv('EG_APNS_ENVIRONMENT', 'production')
    app = create_app(tmp_path / 'db.sqlite3', start_worker=False)
    headers = {'Authorization': 'Bearer ' + 'a' * 40,
               'X-EG-Installation-ID': '00000000-0000-4000-8000-000000000001'}
    push_headers = headers | {'X-EG-Push-Key': 'ab' * 32}
    registration = dict(token='cd' * 32, environment='production', topic='com.evidenceguard.integration')
    with TestClient(app) as client:
        assert client.put('/api/push/device', headers=push_headers, json=registration).json()['enabled']
        device = client.post('/api/devices/import', headers=headers, json=dict(accountId='test-account', platform='ios',
            devices=[dict(sn='T8171TEST0001', model='T8171', name='Test camera')])).json()[0]
        session = client.post('/api/media-sessions', headers=headers, json=dict(deviceId=device['id'], platform='ios')).json()
        media_headers = headers | {'X-EG-Media-Session': session['token']}
        url = '/api/media-sessions/' + session['id']
        heartbeat = dict(state='streaming', sequence=1, frameAgeMs=0)
        assert client.post(url + '/heartbeat', headers=media_headers, json=heartbeat).status_code == 200
        # The two private proofs must never authorize each other's endpoints.
        assert client.get('/api/push/status', headers=media_headers).status_code == 403
        assert client.get(url + '/commands', headers=push_headers).status_code == 404
        assert not client.delete('/api/push/device', headers=push_headers).json()['enabled']
        assert client.post(url + '/heartbeat', headers=media_headers, json=heartbeat).status_code == 200
        assert client.put('/api/push/device', headers=push_headers, json=registration).json()['enabled']
        assert client.post(url + '/stop', headers=media_headers).json()['status'] == 'stopped'
        assert client.get('/api/push/status', headers=push_headers).json()['enabled']


@pytest.mark.parametrize('direct_vision', [True, False])
def test_agent_receives_challenged_live_image_or_completed_visual_review(tmp_path, monkeypatch, direct_vision):
    async def run():
        monkeypatch.setenv('EG_MODEL_VISION', '1' if direct_vision else '0')
        messages = []
        answers = iter([
            dict(role='assistant', content=None, tool_calls=[dict(id='look', type='function',
                function=dict(name='request_camera_snapshot', arguments='{}'))]),
            dict(role='assistant', content='收到本次请求的测试图片。'),
        ])
        class Provider:
            name = 'test'; ready = True
            async def complete(self, history, tools):
                messages.append(json.loads(json.dumps(history)))
                return next(answers)
        app = create_app(tmp_path/'agent.sqlite3', start_worker=False, provider=Provider())
        hub = app.state.camera.live
        device = imported(hub)
        _, session = ready(hub, device['id'])
        vision = app.state.visual_review.provider
        vision.ready = True
        vision.describe_observations = AsyncMock(return_value=dict(visible=['蓝灰色测试画面'], uncertainties=[]))
        value = app.state.agent.start('现在画面里有什么？', 'test-chat', camera_id=device['id'])
        for _ in range(100):
            commands = hub.commands(session)
            if commands: break
            await asyncio.sleep(.01)
        assert commands
        raw = picture(commands[0]['requestId'])
        hub.upload(session, FrameUpload(**raw))
        await asyncio.wait_for(asyncio.gather(*list(app.state.agent.tasks.values())), 3)
        result = app.state.store.run(value['id'])
        assert result['status'] == 'completed'
        assert result['captures'][0]['cameraId'] == device['id']
        assert result['captures'][0]['visionAvailable'] is True
        if direct_vision:
            assert messages[-1][-1]['content'][1]['image_url']['url'].endswith(raw['imageBase64'])
            vision.describe_observations.assert_not_called()
        else:
            vision.describe_observations.assert_awaited_once()
            assert vision.describe_observations.call_args.args[0][0][0] == base64.b64decode(raw['imageBase64'])
            assert json.loads(messages[-1][-1]['content'])['visualReview']['status'] == 'completed'
        assert app.state.store.skills() == []
        await app.state.agent.shutdown()
        await app.state.camera.live.shutdown()
        app.state.store.close()
    asyncio.run(run())
