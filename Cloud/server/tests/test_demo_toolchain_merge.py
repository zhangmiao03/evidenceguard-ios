"""Cloud-only fixes must coexist with the repository hardware contracts."""
import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from evidenceguard.app import create_app
from evidenceguard.camera.watch import WatchOptions
from evidenceguard.harness.tools import build_tools
from test_harness import ScriptedProvider, settle
from test_hardware_tools import env, host, call, claim, finish


@pytest.mark.parametrize('platform', ['ios', 'web', None])
def test_new_and_legacy_clients_retain_platform_memory_and_private_scope(tmp_path, platform):
    provider=ScriptedProvider([{'role':'assistant','content':'当前没有可确认的设备。'}])
    app=create_app(tmp_path/'compat.sqlite3',provider=provider,start_worker=False)
    with TestClient(app) as client:
        installation=str(uuid4());client.headers['X-EG-Installation-ID']=installation
        # A client without the new optional fields remains usable.
        assert client.get('/api/personal').status_code==200
        assert client.put('/api/personal/memory-options?enabled=false').json()['automaticMemory']['enabled'] is False
        body=dict(message='目前能使用什么？',conversationId='merge-'+str(uuid4()),requestId='merge-'+str(uuid4()))
        if platform: body['clientPlatform']=platform
        response=client.post('/api/agent/runs',json=body)
        assert response.status_code==202,response.text
        run=client.portal.call(settle,app.state.agent,response.json())
        assert run['status']=='completed' and run['clientPlatform']==platform
        assert 'read_phone_context' not in run['executionContract']['allowed_tools']
        assert app.state.store.db.execute('SELECT COUNT(*) FROM memory_jobs').fetchone()[0]==0
        # Existing installations can opt into the stronger private binding.
        secret='private-test-'+('x'*40)
        app.state.connectors.proof(installation,secret,bind=True)
        assert client.get('/api/personal').status_code==403
        client.headers['X-EG-Private-Key']=secret
        assert client.get('/api/personal').status_code==200
        assert client.get('/api/hardware/snapshot').status_code==200


def test_connector_wrapper_preserves_validated_hardware_scope_and_history_restrictions(env):
    app,client=env;device,body,executor,headers=host(client)
    revision=client.get('/api/hardware/snapshot').json()['devices'][0]['capabilityRevision']
    client.post('/api/hardware/validations',json=dict(deviceId=device['id'],tool='device_state_get',capabilityRevision=revision,status='passed',evidence='Explicit integration test double, not physical device verification'))
    run=dict(id='merge-scoped',conversationId='merge',clientPlatform='web')
    base=build_tools(app.state.store,app.state.camera,app.state.hardware.captures,camera_id=device['id'],run=run)
    wrapped=app.state.connectors.tools(base,client.headers['X-EG-Installation-ID'])
    assert 'device_state_get' in wrapped.names and 'read_phone_context' in wrapped.names
    assert 'read_phone_context' not in base.names
    assert 'device_settings_set' not in wrapped.names  # No validation proof for this control.
    historical=app.state.connectors.tools(build_tools(app.state.store,app.state.camera,app.state.hardware.captures,execution_mode='history',run=run),client.headers['X-EG-Installation-ID'])
    assert not set(historical.names)&{'device_state_get','device_settings_set','camera_ptz_step','camera_observe','camera_stop'}


def test_cloud_scheduled_watch_respects_unknown_hardware_control(env):
    app,client=env;device,body,executor,headers=host(client)
    op=call(client,device,'device_settings_set',dict(deviceId=device['id'],field='statusLED',value=True,expectedSettingsRevision=0)).json()
    client.post('/api/hardware/confirmations',json=dict(operationId=op['id'],requestHash=op['requestHash'],decision='approve'))
    dispatched=claim(client,executor,headers)['operation'];finish(client,executor,headers,dispatched,'unknown')
    assert app.state.hardware.busy(device['id'])
    app.state.watch.visual.review=AsyncMock()
    client.portal.call(app.state.watch.configure,device['id'],WatchOptions(enabled=True))
    assert client.portal.call(app.state.watch.step)
    assert app.state.watch.get(device['id'])['status']=='unavailable'
    app.state.watch.visual.review.assert_not_awaited()
    assert app.state.store.db.execute('SELECT COUNT(*) FROM camera_observations').fetchone()[0]==0
    assert app.state.store.db.execute('SELECT COUNT(*) FROM proactive_jobs').fetchone()[0]==0
