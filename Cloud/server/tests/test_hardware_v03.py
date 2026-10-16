"""v0.3 gateway semantics with test executors; no device I/O."""
import time
from types import SimpleNamespace
import pytest
from test_hardware_tools import env, host, call, claim, finish


def ptz_host(c,app):
    routes={name:dict(ready=True,sdkMapping='test-double') for name in ['device_state_get','camera_observe','camera_ptz_step','device_settings_set']}
    routes['camera_ptz_step'].update(motionModes=['step','continuous'],maxContinuousMs=1100)
    d,_,h,headers=host(c,extra={'sdkVersion':'2.2.7','routes':routes})
    device=c.get('/api/hardware/snapshot').json()['devices'][0]
    ref=dict(id='ref_test_only',kind='observation',team='product',deviceId=d['id'],taskId='device:'+d['id'],
             executorId=h['executorId'],validUntil=time.time()+60,viewRevision=device['viewRevision'],
             capabilityRevision=device['capabilityRevision'])
    with app.state.hardware.runtime.store.transaction(): app.state.hardware.runtime.store.put('ref',ref)
    args=dict(deviceId=d['id'],direction='LEFT',referenceObservationId=ref['id'],expectedViewRevision=device['viewRevision'])
    return d,h,headers,device,args


def approve(c,op):
    r=c.post('/api/hardware/confirmations',json=dict(operationId=op['id'],requestHash=op['requestHash'],decision='approve'))
    assert r.status_code==200,r.text


def test_single_step_proof_never_unlocks_continuous_and_field_proof_is_explicit(env):
    app,c=env;d,h,headers,device,args=ptz_host(c,app)
    proof=dict(deviceId=d['id'],tool='camera_ptz_step',variant='step',capabilityRevision=device['capabilityRevision'],
               status='passed',evidence='测试执行器单步范围，不代表真实硬件验收')
    assert c.post('/api/hardware/validations',json=proof).status_code==200
    assert call(c,d,'camera_ptz_step',args,diagnostic=False).json()['executionState']=='awaitingApproval'
    continuous=args | dict(motionMode='continuous',durationMs=500)
    assert call(c,d,'camera_ptz_step',continuous,diagnostic=False).json()['code']=='NOT_VALIDATED'
    assert call(c,d,'camera_ptz_step',args | dict(durationMs=500)).json()['code']=='UNSUPPORTED_PARAMETER'
    assert call(c,d,'camera_ptz_step',args | dict(motionMode='continuous')).json()['code']=='UNSUPPORTED_PARAMETER'
    proof.update(tool='device_settings_set',variant='default')
    assert c.post('/api/hardware/validations',json=proof).json()['code']=='UNSUPPORTED_PARAMETER'


@pytest.mark.parametrize('stop',['acknowledged','unknown',None])
def test_paired_stop_and_result_review_do_not_confuse_acceptance_with_effect(env,stop):
    app,c=env;d,h,headers,device,args=ptz_host(c,app)
    op=call(c,d,'camera_ptz_step',args | dict(motionMode='continuous',durationMs=500)).json()
    approve(c,op); leased=claim(c,h,headers)['operation']
    r=finish(c,h,headers,leased,sdkAccepted=True,stopResult={'state':stop} if stop else None)
    assert r.status_code==200,r.text
    result=r.json()
    assert result['sdkAccepted'] is True and result['observedEffect']=='unconfirmed'
    assert result['humanVerified'] is False
    assert result['executionState']==('completed' if stop=='acknowledged' else 'unknown')
    device2=c.get('/api/hardware/snapshot').json()['devices'][0]
    assert device2['viewRevision']==device['viewRevision']+1 and device2['viewConfirmationRequired']
    review=c.post('/api/hardware/review',json=dict(operationId=op['id'],requestHash=op['requestHash'],
        observedEffect='not_observed',evidence='测试人工复核未观察到效果，不解锁未知占用'))
    assert review.status_code==200,review.text
    assert review.json()['humanVerified'] and review.json()['observedEffect']=='not_observed'
    assert review.json()['executionState']==result['executionState']
    assert 'leaseReleasedByHuman' not in review.json()
    assert not c.get('/api/hardware/snapshot').json()['devices'][0]['validationResults']


def test_current_guard_prevents_control_at_request_and_dispatch(env):
    app,c=env;d,_,h,headers=host(c)
    gateway=app.state.hardware
    args=dict(deviceId=d['id'],field='statusLED',value=True,expectedSettingsRevision=0)
    op=call(c,d,'device_settings_set',args).json();approve(c,op)
    gateway.scenes=SimpleNamespace(list_all=lambda:[dict(cameraId=d['id'],status='active')])
    assert call(c,d,'device_settings_set',args).json()['code']=='ACTIVE_SKILL'
    assert claim(c,h,headers)['command'] is None
    result=next(o for o in c.get('/api/hardware/snapshot').json()['operations'] if o['id']==op['id'])
    assert result['executionState']=='failed' and result['error']['code']=='ACTIVE_SKILL'


def test_bitrate_or_callback_counter_cannot_become_decoder_proof():
    from evidenceguard.hardware_tools.vendor.camera_tools.verification import check_frame
    from evidenceguard.hardware_tools.vendor.camera_tools.catalog import ToolError
    now=time.time()*1000
    frame=dict(sourceKind='decoded_live_frame',deviceId='test',sessionId='session',sequence=10,previousSequence=9,
               dimensions=[96,64],playState='playing',progressSource='bitrate',lastFrameAt=now-10,capturedAt=now)
    with pytest.raises(ToolError): check_frame(frame,'test',now)
    frame['progressSource']='decoder_callback';frame['previousSequence']=10
    with pytest.raises(ToolError): check_frame(frame,'test',now)
    frame['previousSequence']=9;frame['lastFrameAt']=now-3000
    with pytest.raises(ToolError): check_frame(frame,'test',now)


def test_official_android_reference_cannot_authorize_ios(env):
    app,c=env;d,_,h,headers=host(c,extra={'sdkVersion':'2.2.7','sdkArtifactHash':'27916001d9f973361910e2a59da3a870f540f3038816dfc6141b3d33c633f87a'})
    value=call(c,d,'device_inspect').json()
    assert value['referenceBaselines']==[] and value['validations']==[]
    assert call(c,d,diagnostic=False).json()['code']=='NOT_VALIDATED'


def test_legacy_receipt_cannot_borrow_new_executor_validation_scope(env):
    app,c=env;d,h,headers,_,args=ptz_host(c,app)
    op=call(c,d,'camera_ptz_step',args).json();approve(c,op)
    leased=claim(c,h,headers)['operation']
    assert finish(c,h,headers,leased).status_code==200
    store=app.state.hardware.runtime.store
    with store.transaction():
        value=store.get('operation',op['id'])
        value.pop('validationScope');value.pop('artifactValidated')
        store.put('operation',value)
    result=c.post('/api/hardware/review',json=dict(operationId=op['id'],requestHash=op['requestHash'],
        observedEffect='confirmed',evidence='旧版本操作只能查看，不能借用当前设备范围'))
    assert result.status_code==409 and result.json()['code']=='STALE_REFERENCE'
    assert store.get('operation',op['id'])['executionState']=='completed'
