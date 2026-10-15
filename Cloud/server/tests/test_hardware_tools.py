"""Product HTTP/lease tests with explicit executor doubles, never a hardware claim."""
import asyncio
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from evidenceguard.app import create_app
from evidenceguard.hardware_tools.vendor.camera_tools.catalog import ToolError
from evidenceguard.harness.tools import build_tools
from test_live_devices import picture


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv('EG_CAMERA_SOURCE', 'official_sdk')
    app = create_app(tmp_path/'integration.sqlite', start_worker=False)
    with TestClient(app) as c:
        c.headers['X-EG-Installation-ID'] = str(uuid4())
        yield app, c


def register(c, *, model='T8171', platform='ios', media=None, extra=None):
    r = c.post('/api/devices/import', json=dict(accountId='test-account', platform=platform,
        devices=[dict(sn=model+'TESTTOOLS1', model=model, name='测试设备')]))
    assert r.status_code == 200, r.text
    device = r.json()[0]
    routes = {name: dict(ready=True, sdkMapping='test_double') for name in (
        ['camera_observe'] if platform == 'web' else ['camera_observe','device_state_get','device_settings_set','camera_ptz_step'])}
    body = dict(deviceId=device['id'], model=model, platform=platform, adapterVersion='test-only-1',
        sdkArtifactHash='a'*64, firmwareVersion='test-firmware', privacy='unknown' if platform=='web' else 'off',
        officialIdentityReady=True, routes=routes, fields={'statusLED':dict(writable=True,schema={'type':'boolean'})})
    if media: body.update(sessionId=media['id'],mediaToken=media['token'])
    body.update(extra or {})
    return device, body, c.post('/api/hardware/executors', json=body)


def host(c, **kwargs):
    d, body, r = register(c, **kwargs)
    assert r.status_code == 200, r.text
    h = r.json()
    return d, body, h, {'X-EG-Executor-Token':h['token']}


def call(c, d, name='device_state_get', args=None, key=None, diagnostic=True, **kwargs):
    return c.post('/api/hardware/call', json=dict(name=name,arguments=args or {'deviceId':d['id']},
        idempotencyKey=key or str(uuid4()),platform='web',diagnostic=diagnostic,**kwargs))


def claim(c,h,headers):
    r=c.post('/api/hardware/executors/'+h['executorId']+'/claim',json={},headers=headers)
    assert r.status_code == 200,r.text
    return r.json()


def finish(c,h,headers,op,status='acknowledged',**kwargs):
    return c.post('/api/hardware/executors/'+h['executorId']+'/result',headers=headers,
        json=dict(operationId=op['id'],leaseToken=op['leaseToken'],status=status,simulated=False,sdkUsed=True,**kwargs))


def start_live(c,d,platform='ios'):
    r=c.post('/api/media-sessions',json={'deviceId':d['id'],'platform':platform})
    assert r.status_code == 201,r.text
    session=r.json(); headers={'X-EG-Media-Session':session['token']}
    assert c.post('/api/media-sessions/'+session['id']+'/heartbeat',json=dict(state='streaming',sequence=1,frameAgeMs=0),headers=headers).status_code==200
    return session,headers


def test_executor_token_is_bound_to_installation_and_fields_are_closed(env):
    app,c=env; d,body,h,headers=host(c)
    stolen=headers | {'X-EG-Installation-ID':str(uuid4())}
    assert c.post('/api/hardware/executors/'+h['executorId']+'/claim',headers=stolen,json={}).status_code==403
    assert c.post('/api/hardware/executors/'+h['executorId']+'/claim',json={}).status_code==403
    assert 'token' not in c.get('/api/hardware/snapshot').text
    body['fields']['arbitrarySDKMethod']={}
    assert c.post('/api/hardware/executors',json=body).json()['code']=='UNSUPPORTED_FIELD'


def test_discovery_identity_and_sdk_artifact_are_required(env):
    app,c=env; d,body,h,headers=host(c)
    body['deviceId']='sdk-not-imported'
    assert c.post('/api/hardware/executors',json=body).json()['code']=='DEVICE_NOT_REGISTERED'
    body['sdkArtifactHash']='unknown'
    assert c.post('/api/hardware/executors',json=body).status_code==422


@pytest.mark.parametrize('model',['T8171','T8214'])
def test_read_and_control_receipts_confirmation_and_idempotency(env,model):
    app,c=env; d,_,h,headers=host(c,model=model)
    args=dict(deviceId=d['id'],field='statusLED',value=True,expectedSettingsRevision=0)
    op=call(c,d,'device_settings_set',args,key='one-action').json()
    assert op['executionState']=='awaitingApproval' and op['executorPlatform']=='iOS'
    assert claim(c,h,headers)['command'] is None
    wrong=c.post('/api/hardware/confirmations',json=dict(operationId=op['id'],requestHash='different',decision='approve'))
    assert wrong.json()['code']=='STALE_REFERENCE'
    assert c.post('/api/hardware/confirmations',json=dict(operationId=op['id'],requestHash=op['requestHash'],decision='approve')).status_code==200
    dispatched=claim(c,h,headers)['operation']
    r=finish(c,h,headers,dispatched)
    assert r.status_code==200,r.text
    assert r.json()['executionState']=='completed' and r.json()['physicalResult']=='unverified'
    assert finish(c,h,headers,dispatched).json()==r.json()
    assert call(c,d,'device_settings_set',args,key='one-action').json()['id']==op['id']
    assert claim(c,h,headers)['command'] is None
    args['value']=False
    assert call(c,d,'device_settings_set',args,key='one-action').json()['code']=='IDEMPOTENCY_CONFLICT'


@pytest.mark.parametrize('stop_first',[True,False])
def test_stop_dispatch_bypasses_capture_gate_and_late_execution_cannot_undo_stop(env,stop_first):
    app,c=env; d,_,h,headers=host(c)
    op=call(c,d).json(); dispatched=claim(c,h,headers)['operation']
    assert call(c,d,'camera_stop',{'operationId':op['id']}).status_code==200
    gate=app.state.hardware.captures.gate(d['id']); c.portal.call(gate.acquire)
    try: assert claim(c,h,headers)['command']=='stop'
    finally: c.portal.call(gate.release)
    if stop_first:
        assert finish(c,h,headers,dispatched,'stopped',command='stop').json()['executionState']=='cancelled'
        assert finish(c,h,headers,dispatched,command='execute').json()['executionState']=='cancelled'
    else:
        assert finish(c,h,headers,dispatched,command='execute').json()['executionState']=='verifying'
        assert finish(c,h,headers,dispatched,'stopped',command='stop').json()['executionState']=='cancelled'


def test_live_challenge_becomes_product_evidence_and_scoped_observation(env):
    app,c=env; d,_,h,headers=host(c); media,mh=start_live(c,d)
    op=call(c,d,'camera_observe').json(); dispatched=claim(c,h,headers)['operation']
    assert finish(c,h,headers,dispatched,references=[{'kind':'observation'}]).json()['code']=='UNSUPPORTED_ROUTE'
    p,identity=app.state.hardware.executor(c.headers['X-EG-Installation-ID'],h['executorId'],h['token'])
    body=dict(operationId=op['id'],leaseToken=dispatched['leaseToken'])
    future=c.portal.start_task_soon(app.state.hardware.observe,p,identity,body)
    duplicate=c.portal.start_task_soon(app.state.hardware.observe,p,identity,body)
    commands=[]
    for _ in range(100):
        commands=c.get('/api/media-sessions/'+media['id']+'/commands',headers=mh).json()
        if commands: break
        time.sleep(.01)
    assert len(commands)==1
    c.post('/api/media-sessions/'+media['id']+'/heartbeat',json=dict(state='streaming',sequence=2,frameAgeMs=0),headers=mh)
    r=c.post('/api/media-sessions/'+media['id']+'/frames',json=picture(commands[0]['requestId']),headers=mh)
    assert r.status_code==200,r.text
    result=future.result(timeout=4); assert duplicate.result(timeout=4)==result
    assert result['executionState']=='completed',result
    capture=result['result']['data']['capture']; ref=result['result']['references'][0]
    assert capture['sourceType']=='official_live_ios'
    assert capture['capturedAt'] is None and capture['timestampMeaning']=='client_live_sample'
    assert c.get(capture['imageUrl']).status_code==200 and ref['kind']=='observation'
    assert c.post('/api/hardware/executors/'+h['executorId']+'/observe',json=body,headers=headers).json()==result
    assert len(c.get('/api/captures').json())==1
    args=dict(deviceId=d['id'],direction='LEFT',referenceObservationId=ref['id'],expectedViewRevision=ref['viewRevision'])
    ptz=call(c,d,'camera_ptz_step',args).json(); assert ptz['executionState']=='awaitingApproval',ptz
    c.post('/api/hardware/confirmations',json=dict(operationId=ptz['id'],requestHash=ptz['requestHash'],decision='approve'))
    moving=claim(c,h,headers)['operation']; finish(c,h,headers,moving,'unknown')
    assert app.state.camera.live.current(d['id'])['viewVersion']>0
    assert call(c,d,'camera_ptz_step',args).json()['code']=='STALE_REFERENCE'


def test_web_registration_requires_own_live_session_and_does_not_claim_ptz(env):
    app,c=env
    d,body,_=register(c,platform='web')
    media,mh=start_live(c,d,'web'); body.update(sessionId=media['id'],mediaToken=media['token'])
    r=c.post('/api/hardware/executors',json=body); assert r.status_code==200,r.text
    body['routes']['camera_ptz_step']=dict(ready=True,sdkMapping='not-implemented')
    assert c.post('/api/hardware/executors',json=body).json()['code']=='UNSUPPORTED_ROUTE'
    assert call(c,d,'camera_observe').json()['code']=='PRIVACY_UNCONFIRMED'
    proof=c.post('/api/hardware/devices/'+d['id']+'/privacy-check',json={'evidence':'测试人员确认当前官方会话隐私关闭'})
    assert proof.status_code==200,proof.text
    assert call(c,d,'camera_observe').json()['executionState']=='queued'
    assert call(c,d,'camera_observe',diagnostic=False).json()['code']=='PRIVACY_UNCONFIRMED'
    c.post('/api/media-sessions/'+media['id']+'/stop',json={},headers=mh)
    assert c.post('/api/hardware/devices/'+d['id']+'/privacy-check',json={'evidence':'测试人员确认当前官方会话隐私关闭'}).status_code!=200


def test_unknown_control_blocks_capture_until_explicit_reconciliation(env):
    app,c=env; d,_,h,headers=host(c)
    args=dict(deviceId=d['id'],field='statusLED',value=True,expectedSettingsRevision=0)
    op=call(c,d,'device_settings_set',args).json()
    c.post('/api/hardware/confirmations',json=dict(operationId=op['id'],requestHash=op['requestHash'],decision='approve'))
    command=claim(c,h,headers)['operation']; finish(c,h,headers,command,'unknown')
    assert app.state.hardware.busy(d['id'])
    denied=c.post('/api/hardware/devices/'+d['id']+'/release',json={})
    assert denied.json()['code']=='RESOURCE_BUSY'
    r=c.post('/api/hardware/reconcile',json=dict(operationId=op['id'],requestHash=op['requestHash'],decision='release_after_manual_check',evidence='测试人工已核对设备，没有继续运动'))
    assert r.status_code==200,r.text
    assert r.json()['executionState']=='unknown' and not app.state.hardware.busy(d['id'])


def test_scope_validation_and_history_tools_are_independent(env):
    app,c=env; d,body,h,headers=host(c)
    gateway=app.state.hardware
    run=dict(id='unit-agent',conversationId='conversation')
    live=build_tools(app.state.store,app.state.camera,gateway.captures,camera_id=d['id'],run=run)
    assert 'device_state_get' not in live.names
    revision=c.get('/api/hardware/snapshot').json()['devices'][0]['capabilityRevision']
    c.post('/api/hardware/validations',json=dict(deviceId=d['id'],tool='device_state_get',capabilityRevision=revision,status='passed',evidence='测试替身验证回执，非真实硬件验收'))
    live=build_tools(app.state.store,app.state.camera,gateway.captures,camera_id=d['id'],run=run)
    assert 'device_state_get' in live.names
    history=build_tools(app.state.store,app.state.camera,gateway.captures,execution_mode='history',run=run)
    assert not set(history.names) & {'device_state_get','camera_ptz_step','devices_list','camera_stop'}
    p=gateway.principal('agent','test-agent',[d['id']],'task')
    with pytest.raises(ToolError): gateway.invoke(p,'device_state_get',{'deviceId':d['id']},'task','a','Web',diagnostic=True)
    other=gateway.principal('agent','other-agent',[],'task')
    with pytest.raises(ToolError): gateway.invoke(other,'device_state_get',{'deviceId':d['id']},'task','b','Web')
    body['fields']['statusLED']['writable']=False
    assert c.post('/api/hardware/executors',json=body).status_code==200
    assert c.get('/api/hardware/snapshot').json()['devices'][0]['capabilityRevision']!=revision


def test_disconnect_cancels_queued_and_marks_inflight_unknown(env):
    app,c=env; d,_,h,headers=host(c)
    running=call(c,d).json(); claim(c,h,headers)
    queued=call(c,d).json()
    assert c.post('/api/hardware/executors/'+h['executorId']+'/disconnect',headers=headers,json={}).status_code==200
    ops={o['id']:o for o in c.get('/api/hardware/snapshot').json()['operations']}
    assert ops[running['id']]['executionState']=='unknown' and ops[queued['id']]['executionState']=='cancelled'
    assert c.post('/api/hardware/executors/'+h['executorId']+'/claim',headers=headers,json={}).status_code==403


def test_unknown_firmware_reconnect_revokes_old_hardware_validation(env):
    app,c=env; d,body,h,headers=host(c,extra={'firmwareVersion':'unknown'})
    before=c.get('/api/hardware/snapshot').json()['devices'][0]['capabilityRevision']
    proof=dict(deviceId=d['id'],tool='device_state_get',capabilityRevision=before,
        status='passed',evidence='测试替身检查接口；不代表真实设备验收')
    assert c.post('/api/hardware/validations',json=proof).status_code==200
    op=call(c,d,diagnostic=False).json()
    claimed=claim(c,h,headers)['operation']
    assert claimed['id']==op['id']
    assert finish(c,h,headers,claimed).status_code==200
    assert c.post('/api/hardware/executors',json=body).status_code==200
    after=c.get('/api/hardware/snapshot').json()['devices'][0]
    assert after['capabilityRevision']!=before and after['validationResults']==[]
    assert call(c,d,diagnostic=False).json()['code']=='NOT_VALIDATED'
    assert c.post('/api/hardware/validations',json=proof).json()['code']=='STALE_REFERENCE'


def test_agent_control_waits_for_human_then_updates_the_same_run(env):
    from test_harness import ScriptedProvider, tool, settle
    app,c=env; d,_,h,headers=host(c)
    revision=c.get('/api/hardware/snapshot').json()['devices'][0]['capabilityRevision']
    c.post('/api/hardware/validations',json=dict(deviceId=d['id'],tool='device_settings_set',capabilityRevision=revision,
        status='passed',evidence='测试替身检查接口；不代表真实设备验收'))
    app.state.agent.model_provider=ScriptedProvider([tool('device_settings_set',dict(deviceId=d['id'],field='statusLED',value=True,expectedSettingsRevision=0))])
    async def start():
        return await settle(app.state.agent,app.state.agent.start('打开指示灯','hardware-chat',camera_id=d['id'],client_platform='ios'))
    run=c.portal.call(start)
    assert run['status']=='completed',run
    op=run['hardwareOperations'][0]
    assert op['executionState']=='awaitingApproval' and op['requesterPlatform']=='iOS'
    assert claim(c,h,headers)['command'] is None
    assert c.post('/api/hardware/confirmations',json=dict(operationId=op['id'],requestHash=op['requestHash'],decision='approve')).status_code==200
    dispatched=claim(c,h,headers)['operation']; finish(c,h,headers,dispatched)
    persisted=c.get('/api/runs/'+run['id']).json()['hardwareOperations'][0]
    assert persisted['id']==op['id'] and persisted['executionState']=='completed'
    assert persisted['physicalResult']=='unverified'
    assert 'SDK acknowledged' in app.state.agent.model_provider.messages[0][0]['content']


def test_cancel_agent_run_cancels_its_pending_hardware_without_granting_other_tasks(env):
    from test_harness import ScriptedProvider, tool, settle
    app,c=env; d,_,h,headers=host(c)
    revision=c.get('/api/hardware/snapshot').json()['devices'][0]['capabilityRevision']
    c.post('/api/hardware/validations',json=dict(deviceId=d['id'],tool='device_settings_set',capabilityRevision=revision,
        status='passed',evidence='测试替身检查接口；不代表真实设备验收'))
    app.state.agent.model_provider=ScriptedProvider([tool('device_settings_set',dict(deviceId=d['id'],field='statusLED',value=True,expectedSettingsRevision=0))])
    async def start(): return await settle(app.state.agent,app.state.agent.start('打开指示灯','cancel-chat',camera_id=d['id']))
    run=c.portal.call(start)
    assert c.post('/api/runs/'+run['id']+'/cancel',json={}).status_code==200
    assert c.get('/api/runs/'+run['id']).json()['hardwareOperations'][0]['executionState']=='cancelled'
    assert claim(c,h,headers)['command'] is None
