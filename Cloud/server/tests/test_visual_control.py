"""Product decisions with explicit executor doubles, not iOS hardware validation."""
import asyncio
import json
import time
from unittest.mock import AsyncMock

import pytest
from evidenceguard.vision.control import checked_location,correction
from test_hardware_tools import env,host,start_live,claim,finish
from test_endpoint_vision import picture


@pytest.mark.parametrize('box,direction',[
    ([.05,.4,.1,.1],'LEFT'),([.8,.4,.1,.1],'RIGHT'),([.4,.02,.1,.1],'UP'),
    ([.4,.85,.1,.1],'DOWN'),([.4,.4,.2,.2],None)])
def test_direction_comes_from_current_target_center_not_motion_words(box,direction):
    value=checked_location(dict(visible=True,correspondence='confirmed',box=box,evidence='synthetic target'))
    assert correction(value)==direction


@pytest.mark.parametrize('box',[[1,0,.1,.1],[0,0,float('nan'),.1],[0,0,-.1,.1],[True,0,.1,.1]])
def test_invalid_grounding_cannot_select_a_motor_command(box):
    with pytest.raises(ValueError):checked_location(dict(visible=True,correspondence='confirmed',box=box,evidence='test'))


def test_missing_native_proof_and_doorbell_are_blocked_without_model_call(env):
    app,c=env;d,body,h,headers=host(c)
    controller=app.state.visual_control;controller.enabled=True
    controller.vision.enabled=True;controller.vision.port.ready=True
    start_live(c,d)
    device=app.state.hardware.runtime.store.get('device',d['id'])
    device['routes']['camera_observe']['ready']=False
    app.state.hardware.runtime.store.put('device',device)
    result=controller.readiness(d['id'],c.headers['X-EG-Installation-ID'])
    assert 'NATIVE_DECODER_PROOF_REQUIRED' in result['reasons'] and not result['ready']
    device['model']='T8214';app.state.hardware.runtime.store.put('device',device)
    assert 'NO_MECHANICAL_PTZ' in controller.readiness(d['id'],c.headers['X-EG-Installation-ID'])['reasons']


@pytest.mark.parametrize('view_changes_during_verification',[False,True])
def test_one_confirmed_step_then_visual_verification_no_automatic_second_step(env,view_changes_during_verification):
    app,c=env;d,body,h,headers=host(c);session,_=start_live(c,d)
    controller=app.state.visual_control;controller.enabled=True
    controller.vision.enabled=True;controller.vision.port.ready=True
    owner=c.headers['X-EG-Installation-ID']; now=time.time()
    hardware=app.state.hardware;device=hardware.runtime.store.get('device',d['id'])
    for tool in ('camera_observe','camera_ptz_step'):
        r=c.post('/api/hardware/validations',json=dict(deviceId=d['id'],tool=tool,
            capabilityRevision=device['capabilityRevision'],status='passed',evidence='SCRIPTED TEST ONLY, no physical hardware'))
        assert r.status_code==200,r.text
    store=app.state.store
    def frame(key,at):return picture(store,key,at,device_id=d['id'])|{'cameraId':d['id']}
    before,after=frame('before',now),frame('after',now+.2)
    scene=dict(id='control-scene',clientId=owner,cameraId=d['id'],revision=1,status='paused',
        frame=frame('baseline',now-10),box=dict(x=.1,y=.2,width=.1,height=.2),plan=dict(target='测试方块',selection='object'))
    app.state.visual_scenes.save(scene,now+100)
    run=dict(id='control-run',clientId=owner,clientPlatform='ios',cameraId=d['id'],conversationId='control-conversation',status='running',createdAt=now)
    store.save_run(run)
    ref=dict(id='ref-test-observation',kind='observation',deviceId=d['id'],team='product',
        taskId='conversation:control-conversation',executorId=h['executorId'],validUntil=now+30,
        capabilityRevision=device['capabilityRevision'],viewRevision=device['viewRevision'])
    hardware.runtime.store.put('ref',ref)
    controller.observe=AsyncMock(side_effect=[(before,ref),(after,ref)])
    left=dict(visible=True,correspondence='confirmed',box=[.1,.3,.1,.2],evidence='synthetic left')
    center=dict(visible=True,correspondence='confirmed',box=[.4,.4,.2,.2],evidence='synthetic center')
    async def locate(scene,capture):
        if capture['frameId']==after['frameId']:
            if view_changes_during_verification: hardware.cameras.live.invalidate_view(d['id'])
            return center,{}
        return left,{}
    controller.locate=AsyncMock(side_effect=locate)
    result=c.portal.call(controller.aim,scene['id'],1,run)
    assert result['status']=='awaitingApproval',result
    operation=result['operation']
    assert operation['tool']=='camera_ptz_step' and operation['arguments']['direction']=='LEFT'
    assert claim(c,h,headers)['command'] is None
    duplicate=c.portal.call(controller.aim,scene['id'],1,run)
    assert duplicate['operationId']==result['operationId'] and controller.locate.await_count==1
    response=c.post('/api/hardware/confirmations',json=dict(operationId=operation['id'],requestHash=operation['requestHash'],decision='approve'))
    assert response.status_code==200,response.text
    dispatched=claim(c,h,headers)['operation']
    assert finish(c,h,headers,dispatched,sdkAccepted=True).status_code==200
    async def settle():await asyncio.gather(*list(controller.tasks.values()))
    c.portal.call(settle)
    value=controller.result(result['id'],owner)
    if view_changes_during_verification:
        assert value['status']=='unknown' and 'centerOffsetImprovement' not in value
    else:
        assert value['status']=='verified_observation' and value['centered']
        assert value['centerOffsetImprovement']>0 and not value['humanVerified']
    operations=hardware.runtime.store.all('operation','product')
    assert sum(op['tool']=='camera_ptz_step' for op in operations)==1
    assert hardware.runtime.store.get('operation',operation['id'])['observedEffect']=='unconfirmed'
    with pytest.raises(KeyError):controller.result(result['id'],'other-installation')


def test_existing_chat_card_contract_and_history_scope_are_preserved(tmp_path,monkeypatch):
    from evidenceguard.app import create_app
    from evidenceguard.ops import PRIVATE_CONTENT
    from test_harness import ScriptedProvider,settle,tool
    monkeypatch.setenv('EG_VISUAL_CONTROL_ENABLED','1')
    async def check():
        provider=ScriptedProvider([tool('aim_camera_at_guard_target',{'guard_id':'g','revision':1}),
                                   {'role':'assistant','content':'历史检索'}])
        app=create_app(tmp_path/'card.sqlite',start_worker=False,provider=provider)
        async def aim(*args):
            assert PRIVATE_CONTENT.get()
            return dict(id='visual-job',status='awaitingApproval',operation=dict(id='op_test',
                executionState='awaitingApproval',tool='camera_ptz_step',deviceId='sdk-test'))
        app.state.visual_control.aim=AsyncMock(side_effect=aim)
        runtime=app.state.agent
        args=dict(client_id='control-client',client_platform='ios',connector_access=True,guard_flow_version=1)
        run=await settle(runtime,runtime.start('把目标调到中央','control-chat',**args))
        assert run['status']=='completed' and run['privateContent']
        assert run['hardwareOperations'][0]['tool']=='camera_ptz_step'
        assert run['hardwareOperations'][0]['visualControlId']=='visual-job'
        assert provider.complete.await_count==1
        history=await settle(runtime,runtime.start('查历史','control-history',execution_mode='history',**args))
        for name in ('aim_camera_at_guard_target','sample_camera_vision','read_visual_control'):
            assert name not in history['executionContract']['allowed_tools']
        await runtime.scheduler.shutdown();app.state.store.close()
    asyncio.run(check())
