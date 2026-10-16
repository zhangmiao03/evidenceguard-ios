"""Isolated scene workflow checks. Images/cameras/models here are test doubles."""
import asyncio
import copy
import io
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image
from evidenceguard.store import Store
from evidenceguard.personal import PersonalAgent
from evidenceguard.proactive import ProactiveEngine
from evidenceguard.visual_skills.schema import Create, Interpret, ScenePlan, Selection, Judgment
from evidenceguard.visual_skills.service import VisualScenes
from evidenceguard.visual_skills.harness import SceneHarness


PLAN = dict(title='门口包裹看护', target='门口这个包裹', selection='object', trigger='leaves',
            confirmationSeconds=15, completion='continuous')
CLIENT = '2c322328-71f2-4c2f-ac05-1cc27c3c4342'
OTHER = 'c58ab789-506e-49ea-a14f-270ce80093e6'


def test_result_distinguishes_confirmed_rules_from_fresh_evidence(env):
    async def check():
        scenes, store, _, _ = env
        scene = await selected(env)
        assert scenes.public(scene)['result']['state'] == 'pending'
        scene = await scenes.activate(scene['id'], CLIENT, scene['revision'])
        assert scenes.result(scene)['state'] == 'unknown'
        now = time.time()
        scenes.advance(scene, dict(state='inside', reason='包裹在区域内'), frame(store, now, 'normal'), now)
        assert scenes.result(scene, now)['state'] == 'confirmed'
        assert scenes.result(scene, now + 61)['state'] == 'unknown'
        scenes.advance(scene, dict(state='outside', reason='区域内未见包裹'), frame(store, now+16, 'outside-1'), now+16)
        assert scenes.result(scene, now+16)['state'] == 'checking'
        assert scenes.advance(scene, dict(state='outside', reason='区域内仍未见包裹'), frame(store, now+32, 'outside-2'), now+32)
        assert scenes.result(scene, now+32)['state'] == 'issue'
        scenes.advance(scene, dict(state='inside', reason='包裹重新可见'), frame(store, now+48, 'normal-2'), now+48)
        assert scenes.result(scene, now+48)['state'] == 'confirmed'
        scenes.advance(scene, dict(state='unknown', reason='画面遮挡'), None, now+64)
        assert scenes.result(scene, now+64)['state'] == 'unknown'
    asyncio.run(check())


def test_missing_initial_baseline_does_not_claim_normal_or_invent_departure(env):
    async def check():
        scenes, store, _, _ = env
        scene = await selected(env)
        scene = await scenes.activate(scene['id'], CLIENT, scene['revision'])
        now = time.time()
        for i in range(4):
            at = now+i*16
            assert not scenes.advance(scene, dict(state='outside', reason='未见目标'), frame(store, at, str(i)), at)
        assert scenes.result(scene, at)['state'] == 'unknown'
    asyncio.run(check())


@pytest.mark.parametrize('matches', [False, True])
def test_reconnection_needs_explicit_reference_alignment_and_new_baseline(env, matches):
    async def check():
        scenes, store, captures, harness = env
        scene = await selected(env)
        scene['frame']['viewRevision'] = 'live-original:0'
        with store.transaction(): scenes.save(scene)
        scene = await scenes.activate(scene['id'], CLIENT, scene['revision'])
        scene['observation'].update(armed=True, since=time.time()-20, count=2)
        with store.transaction(): scenes.save(scene, time.time()-1)
        captures.capture.return_value = frame(store, key='reconnected') | dict(viewRevision='live-new:0')
        harness.observe.return_value = dict(state='outside', regionClear=True, identityClear=False,
                                           viewMatchesReference=matches, reason='区域内未见目标')
        await scenes.step()
        updated = scenes.get(scene['id'], CLIENT)
        assert not updated['observation']['armed']
        assert not scenes.proactive.messages(CLIENT)
        if matches:
            assert updated['validatedViewRevision'] == 'live-new:0'
            assert updated['observation']['state'] == 'outside'
        else:
            assert updated['validatedViewRevision'] == 'live-original:0'
            assert updated['observation']['state'] == 'unknown'
    asyncio.run(check())


def test_health_notice_is_scoped_deduplicated_and_resets_on_recovery(env):
    from evidenceguard.personal import Preferences
    async def check():
        scenes, store, _, _ = env
        scenes.proactive.personal.preferences(CLIENT, Preferences(enabled=True, quietStart=0, quietEnd=0))
        scene = await selected(env)
        scene = await scenes.activate(scene['id'], CLIENT, scene['revision'])
        now = time.time()
        scene['healthSince'] = now-121
        with store.transaction():
            scenes.check_health(scene, now)
            scenes.check_health(scene, now+10)
            scenes.save(scene)
        assert len(scenes.proactive.messages(CLIENT)) == 1
        assert scenes.proactive.messages(OTHER) == []
        assert store.evidence() == []  # An unavailable check is not fabricated camera evidence.
        again = scenes.get(scene['id'], CLIENT)
        with store.transaction(): scenes.check_health(again, now+20)
        assert len(scenes.proactive.messages(CLIENT)) == 1
        scenes.advance(again, dict(state='inside', reason='目标可见'), frame(store, now+30), now+30)
        scenes.check_health(again, now+30)
        assert not again['healthNotified']
        scenes.advance(again, dict(state='unknown', reason='断流'), None, now+40)
        with store.transaction():
            scenes.check_health(again, now+40)
            scenes.check_health(again, now+161)
        assert len(scenes.proactive.messages(CLIENT)) == 2
    asyncio.run(check())


def test_health_notice_respects_opt_out_and_quiet_hours(env):
    from evidenceguard.personal import Preferences
    from datetime import datetime, timezone
    async def check():
        scenes, store, _, _ = env
        scene = await selected(env)
        scene = await scenes.activate(scene['id'], CLIENT, scene['revision'])
        now = time.time(); scene['healthSince'] = now-121
        with store.transaction(): scenes.check_health(scene, now)
        assert scenes.proactive.messages(CLIENT) == []
        hour = datetime.fromtimestamp(now, timezone.utc).hour
        scenes.proactive.personal.preferences(CLIENT, Preferences(enabled=True, quietStart=hour, quietEnd=(hour+1)%24))
        with store.transaction(): scenes.check_health(scene, now)
        assert scenes.proactive.messages(CLIENT) == []
        assert not scene['healthNotified']
    asyncio.run(check())


@pytest.fixture
def env(tmp_path):
    store = Store(tmp_path / 'scene.sqlite3')
    personal = PersonalAgent(store)
    agent = SimpleNamespace()
    proactive = ProactiveEngine(personal, agent)
    proactive.push = None
    cameras = SimpleNamespace(manifests=AsyncMock(return_value=[SimpleNamespace(id='test-device', connection='online')]))
    captures = SimpleNamespace(cameras=cameras, capture=AsyncMock())
    harness = SimpleNamespace(ready=True, interpret=AsyncMock(return_value=dict(plan=PLAN, question='', unsupportedReason='')),
                              observe=AsyncMock(return_value=dict(state='inside', regionClear=True, identityClear=True, reason='测试图中目标可见')))
    scenes = VisualScenes(store, captures, harness, proactive)
    yield scenes, store, captures, harness
    store.close()


async def draft(env, request='request-test-01', client=CLIENT, message='门口这个包裹离开就提醒我'):
    scenes = env[0]
    value = await scenes.create(client, Create(requestId=request, cameraId='test-device', message=message))
    await asyncio.gather(*list(scenes.compiling.values()))
    return scenes.get(value['id'], client)


def frame(store, at=None, key='frame-1', source='official_live_ios'):
    # The production service rejects fixtures. This isolated fake explicitly
    # exercises that contract; it is not actual camera/SDK validation.
    out=io.BytesIO(); Image.new('RGB',(320,180),'white').save(out,format='JPEG')
    media=store.save_media(dict(device_id='test-device', frame_id=key), out.getvalue(), 'image/jpeg')
    return dict(id='capture-'+key, cameraId='test-device', status='completed', mediaId=media['id'], imageUrl=media['imageUrl'],
                frameId=key, sampledAt=at or time.time(), sourceType=source, viewRevision='test-session:0', timestampMeaning='client_live_sample')


async def selected(env):
    scenes, store, captures, _=env
    scene=await draft(env)
    captures.capture.return_value=frame(store)
    scene=await scenes.frame(scene['id'],CLIENT,scene['revision'])
    return scenes.select(scene['id'],CLIENT,Selection(revision=scene['revision'],frameId=scene['frame']['frameId'],
                        box=dict(x=.2,y=.3,width=.3,height=.4)))


def test_three_steps_need_explicit_confirmation_and_are_idempotent(env):
    async def check():
        scenes,store,_,_=env
        scene=await selected(env)
        assert scene['status']=='draft' and scenes.public(scene)['canActivate']
        assert store.skills()==[]  # No changes to legacy tasks.
        assert scenes.proactive.messages(CLIENT)==[]
        active=await scenes.activate(scene['id'],CLIENT,scene['revision'])
        again=await scenes.activate(scene['id'],CLIENT,scene['revision'])
        assert active==again and active['status']=='active'
        assert active['observation']['state']=='unknown'
        assert scenes.proactive.messages(CLIENT)==[]
    asyncio.run(check())


def test_vague_request_stays_in_description_and_does_not_invent_template(env):
    async def check():
        scenes,_,captures,harness=env
        harness.interpret.return_value=dict(plan=None,question='想关注什么，在什么情况下提醒你？',unsupportedReason='')
        scene=await draft(env,message='创建skill，自定义事件')
        assert scene['stage']=='describe' and scene['plan'] is None
        assert not scenes.public(scene)['canActivate']
        with pytest.raises(ValueError): await scenes.frame(scene['id'],CLIENT,scene['revision'])
        captures.capture.assert_not_awaited()
    asyncio.run(check())


def test_followup_keeps_same_draft_full_context_and_invalidates_selection(env):
    async def check():
        scenes,_,_,harness=env
        scene=await selected(env)
        harness.interpret.return_value=dict(plan=PLAN|{'completion':'once'},question='',unsupportedReason='')
        body=Interpret(requestId='edit-request-02',revision=scene['revision'],message='只提醒我一次')
        updating=scenes.interpret(scene['id'],CLIENT,body)
        assert updating['box'] is None and updating['frame'] is None
        await asyncio.gather(*list(scenes.compiling.values()))
        updated=scenes.get(scene['id'],CLIENT)
        sent=harness.interpret.call_args.args[0]
        assert sent['plan']==PLAN and sent['inputs']==['门口这个包裹离开就提醒我','只提醒我一次']
        assert updated['plan']['completion']=='once' and len(scenes.list_all(CLIENT))==1
        assert scenes.interpret(scene['id'],CLIENT,body)==updated
        with pytest.raises(ValueError): scenes.interpret(scene['id'],CLIENT,body.model_copy(update={'requestId':'different-request'}))
    asyncio.run(check())


def test_clients_cannot_read_or_overwrite_other_drafts_even_same_request_id(env):
    async def check():
        scenes=env[0]
        a=await draft(env); b=await draft(env,client=OTHER)
        assert a['id']!=b['id']
        with pytest.raises(KeyError): scenes.get(a['id'],OTHER)
        assert len(scenes.list_all(CLIENT))==len(scenes.list_all(OTHER))==1
        c=await draft(env); assert c['id']==a['id']
    asyncio.run(check())


def test_concurrent_create_retry_compiles_once(env):
    async def check():
        scenes,_,captures,harness=env
        async def discovery():
            await asyncio.sleep(0)
            return [SimpleNamespace(id='test-device',connection='online')]
        captures.cameras.manifests.side_effect=discovery
        body=Create(requestId='concurrent-request',cameraId='test-device',message='看住这个包裹，离开就提醒')
        a,b=await asyncio.gather(scenes.create(CLIENT,body),scenes.create(CLIENT,body))
        await asyncio.gather(*list(scenes.compiling.values()))
        assert a['id']==b['id'] and len(scenes.list_all(CLIENT))==1
        assert harness.interpret.await_count==1
    asyncio.run(check())


@pytest.mark.parametrize('source', ['fixture', 'official_sdk', 'official_live_web', 'replay'])
def test_only_fresh_ios_live_frames_can_bind_selection(env,source):
    async def check():
        scenes,store,captures,_=env; scene=await draft(env)
        captures.capture.return_value=frame(store,source=source)
        with pytest.raises(ValueError): await scenes.frame(scene['id'],CLIENT,scene['revision'])
        assert scenes.get(scene['id'],CLIENT)['frame'] is None
    asyncio.run(check())


def test_selection_rejects_wrong_frame_old_revision_expired_frame_and_bad_box(env):
    async def check():
        scenes,store,captures,_=env; scene=await selected(env)
        body=Selection(revision=scene['revision'],frameId='wrong',box=dict(x=.1,y=.1,width=.3,height=.4))
        with pytest.raises(ValueError): scenes.select(scene['id'],CLIENT,body)
        with pytest.raises(ValueError): scenes.select(scene['id'],CLIENT,body.model_copy(update={'revision':1}))
        captures.capture.return_value=frame(store,at=time.time()-400)
        with pytest.raises(ValueError): await scenes.frame(scene['id'],CLIENT,scene['revision'])
        with pytest.raises(ValueError): Selection(revision=1,frameId='f',box=dict(x=.9,y=0,width=.5,height=.5))
    asyncio.run(check())


def test_unsupported_requirements_remain_saved_and_cannot_activate(env):
    async def check():
        scenes,_,_,harness=env
        harness.interpret.return_value=dict(plan=PLAN,question='',unsupportedReason='暂不支持判断具体是谁。')
        scene=await draft(env,message='看看是谁把包裹拿走了')
        assert scene['stage']=='describe' and not scenes.public(scene)['canActivate']
        with pytest.raises(ValueError): await scenes.activate(scene['id'],CLIENT,scene['revision'])
    asyncio.run(check())


def sample(scenes,scene,state,at,key):
    return scenes.advance(scene,dict(state=state,reason='隔离测试观察'),dict(frameId=key,sampledAt=at),at)


def test_state_change_needs_baseline_distinct_fresh_samples_and_elapsed_time(env):
    scenes=env[0]
    scene=dict(plan=PLAN,observation=scenes.empty_observation(),status='active')
    assert not sample(scenes,scene,'outside',100,'a')  # Cannot establish removal from absence.
    assert not sample(scenes,scene,'outside',120,'b')
    assert not sample(scenes,scene,'inside',130,'c')
    assert not sample(scenes,scene,'outside',145,'d')
    assert not sample(scenes,scene,'outside',160,'d')  # Duplicate frame is never second evidence.
    assert not sample(scenes,scene,'outside',155,'e')  # Only ten seconds.
    assert sample(scenes,scene,'outside',160,'f')
    assert not sample(scenes,scene,'outside',180,'g')  # No repeated alerts until new opposite baseline.
    assert not sample(scenes,scene,'inside',195,'h')
    assert not sample(scenes,scene,'outside',210,'i')
    assert sample(scenes,scene,'outside',225,'j')


@pytest.mark.parametrize('break_kind',['unknown','gap'])
def test_unknown_or_gap_resets_baseline_not_just_timer(env,break_kind):
    scenes=env[0]; scene=dict(plan=PLAN,observation=scenes.empty_observation(),status='active')
    sample(scenes,scene,'inside',100,'a'); sample(scenes,scene,'outside',115,'b')
    if break_kind=='unknown': sample(scenes,scene,'unknown',120,'c'); at=140
    else: at=300
    assert not sample(scenes,scene,'outside',at,'d')
    assert not sample(scenes,scene,'outside',at+20,'e')


def test_entering_region_and_once_completion(env):
    scenes=env[0]; scene=dict(plan=PLAN|dict(selection='region',trigger='enters',completion='once'),observation=scenes.empty_observation(),status='active')
    sample(scenes,scene,'outside',100,'a'); sample(scenes,scene,'inside',115,'b')
    assert sample(scenes,scene,'inside',130,'c') and scene['status']=='completed'


def test_old_inflight_observation_cannot_publish_after_pause(env):
    async def check():
        scenes,store,captures,harness=env; scene=await selected(env)
        active=await scenes.activate(scene['id'],CLIENT,scene['revision'])
        async def observe(*args):
            scenes.pause(active['id'],CLIENT,active['revision'])
            return dict(state='outside',regionClear=True,identityClear=True,reason='旧结果')
        harness.observe.side_effect=observe
        captures.capture.return_value=frame(store,key='fresh')
        assert await scenes.step()
        assert scenes.get(active['id'],CLIENT)['status']=='draft'
        assert scenes.proactive.messages(CLIENT)==[]
    asyncio.run(check())


def test_view_change_and_invalid_model_output_become_unknown(env):
    async def check():
        scenes,store,captures,harness=env; scene=await selected(env)
        active=await scenes.activate(scene['id'],CLIENT,scene['revision'])
        captures.capture.return_value=frame(store,key='new')|dict(viewRevision='changed')
        await scenes.step(); harness.observe.assert_not_awaited()
        assert '视角' in scenes.get(active['id'],CLIENT)['observation']['reason']
        captures.capture.return_value=frame(store,key='new2')
        harness.observe.return_value=dict(state='broken_raw_code')
        await scenes.step(now=time.time()+30)
        state=scenes.get(active['id'],CLIENT)['observation']
        assert state['state']=='unknown' and 'broken_raw_code' not in state['reason']
    asyncio.run(check())


def test_alert_persists_main_conversation_message_and_evidence_for_only_owner(env):
    async def check():
        scenes,store,_,_=env; scene=await selected(env)
        scene['observation'].update(state='outside',reason='测试图中原位置已没有目标')
        receipt=frame(store)
        with store.transaction(): scenes.publish(scene,receipt)
        messages=scenes.proactive.messages(CLIENT)
        assert len(messages)==1 and scenes.proactive.messages(OTHER)==[]
        assert messages[0]['sources'][0]['evidenceId']==scene['evidenceIds'][0]
        assert store.evidence()[0]['imageUrl']==receipt['imageUrl']
    asyncio.run(check())


def test_restart_interrupts_generation_and_resets_active_partial_state(env):
    async def check():
        scenes,store,captures,harness=env; scene=await selected(env)
        active=await scenes.activate(scene['id'],CLIENT,scene['revision'])
        active['observation'].update(armed=True,since=time.time()-30,count=3)
        with store.transaction(): scenes.save(active)
        restarted=VisualScenes(store,captures,harness,scenes.proactive)
        assert not restarted.get(scene['id'],CLIENT)['observation']['armed']
    asyncio.run(check())


def test_compiler_port_has_no_tools_and_passes_full_current_plan():
    async def check():
        provider=SimpleNamespace(complete=AsyncMock(return_value=dict(content=json.dumps(dict(plan=PLAN,question='',unsupportedReason='')))))
        agent=SimpleNamespace(ready=True,executor='bounded-chat-v1',model_provider=provider)
        port=SceneHarness(agent,SimpleNamespace(provider=SimpleNamespace(ready=True)))
        result=await port.interpret(dict(inputs=['看住包裹','只提醒一次'],plan=PLAN,question='',unsupportedReason=''))
        messages,tools=provider.complete.call_args.args
        assert tools==[] and json.loads(messages[1]['content'])['plan']==PLAN
        assert result['plan']==PLAN
        provider.complete.return_value=dict(content='已开启',tool_calls=[dict(name='activate')])
        with pytest.raises(Exception): await port.interpret(dict(inputs=['创建']))
    asyncio.run(check())


def test_scene_schema_rejects_unimplemented_or_nonfinite_fields():
    with pytest.raises(ValueError): ScenePlan.model_validate(PLAN|dict(trigger='barking'))
    with pytest.raises(ValueError): ScenePlan.model_validate(PLAN|dict(script='execute'))
    with pytest.raises(ValueError): ScenePlan.model_validate(PLAN|dict(confirmationSeconds=float('nan')))


def test_api_routes_authenticate_installation_and_keep_scene_private(tmp_path):
    from fastapi.testclient import TestClient
    from evidenceguard.app import create_app
    app=create_app(tmp_path/'routes.sqlite3',start_worker=False)
    with TestClient(app) as client:
        assert client.get('/api/visual-scenes').status_code==409
        assert client.get('/api/visual-scenes',headers={'X-EG-Installation-ID':CLIENT}).json()==[]
        assert client.get('/api/visual-scenes/missing',headers={'X-EG-Installation-ID':CLIENT}).status_code==404


def test_roi_pixels_and_provider_override_do_not_mix_credentials(monkeypatch):
    import base64
    provider=SimpleNamespace(base='https://configured.example/v1',model='doubao-test',key='household-secret',ready=True)
    port=SceneHarness(SimpleNamespace(ready=True),SimpleNamespace(provider=provider))
    monkeypatch.setenv('EG_SCENE_VISION_MODEL_ID','qwen3.8-max')
    assert not port.ready
    assert port.vision_port().key==''
    monkeypatch.setenv('EG_SCENE_VISION_BASE_URL','https://guard.example/v1/')
    monkeypatch.setenv('EG_SCENE_VISION_API_KEY','guard-secret')
    assert port.ready and port.vision_port().key=='guard-secret'
    assert provider.key=='household-secret'
    source=Image.new('RGB',(100,100),'blue')
    for x in range(20,40):
        for y in range(30,60):source.putpixel((x,y),(0,255,0))
    data=io.BytesIO();source.save(data,format='PNG')
    parts=port.image_parts(data.getvalue(),dict(x=.2,y=.3,width=.2,height=.3),'当前')
    crop=Image.open(io.BytesIO(base64.b64decode(parts[3]['image_url']['url'].split(',')[1])))
    assert crop.size==(20,30)
    assert crop.getpixel((10,15))[1]>240  # Actual selected pixels, not the full frame.


@pytest.mark.parametrize('model,option',[('doubao-test','thinking'),('qwen3.8-max','enable_thinking')])
def test_observe_passes_marked_reference_current_roi_and_preserves_alignment_gate(env,monkeypatch,model,option):
    async def check():
        from evidenceguard.harness.providers import OpenAICompatibleProvider
        scenes,store,_,_=env;scene=await selected(env)
        visual=SimpleNamespace(provider=SimpleNamespace(base='https://vision.example/v1',model=model,key='test',ready=True),reserve=lambda *a,**k:None)
        port=SceneHarness(SimpleNamespace(ready=True),visual)
        answer=dict(state='outside',regionClear=True,identityClear=False,viewMatchesReference=True,reason='选框内已没有目标')
        request=AsyncMock(return_value=dict(content=json.dumps(answer)))
        monkeypatch.setattr(OpenAICompatibleProvider,'_request',request)
        result=await port.observe(scene,frame(store,key='current'),store)
        assert result['state']=='outside'  # Absence does not require identifying an absent object.
        messages,options=request.call_args.args
        assert len([p for p in messages[1]['content'] if p['type']=='image_url'])==4
        assert option in options
        answer['viewMatchesReference']=False;request.return_value=dict(content=json.dumps(answer))
        assert (await port.observe(scene,frame(store,key='changed'),store))['state']=='unknown'
    asyncio.run(check())
