"""Guard chat shares the camera editor's drafts; never activates a rule."""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from evidenceguard.visual_skills.chat import for_chat
from evidenceguard.harness.tools import ToolRegistry
from test_visual_scenes import env, CLIENT, OTHER, PLAN
from test_harness import ScriptedProvider, tool, environment, settle


def run(**extra):
    return dict(id='guard-chat-001', clientId=CLIENT, cameraId='test-device', **extra)


def test_shared_record_idempotency_and_owner_scope(env):
    async def check():
        scenes = env[0]
        registry = for_chat(ToolRegistry(), scenes, run())
        first = await registry.call('create_camera_guard', message='狗进入沙发区域时提醒我')
        again = await registry.call('create_camera_guard', message='狗进入沙发区域时提醒我')
        assert first['guardId'] == again['guardId']
        assert len(scenes.list_all(CLIENT)) == 1
        record = scenes.get(first['guardId'], CLIENT)
        assert record['status'] == 'draft' and record['box'] is None
        assert record['prompt'] == '狗进入沙发区域时提醒我'
        assert 'activate_camera_guard' not in registry.names
        other = for_chat(ToolRegistry(), scenes, dict(id='other', clientId=OTHER))
        with pytest.raises(KeyError): await other.call('read_camera_guard', guard_id=first['guardId'])
        assert (await other.call('list_camera_guards'))['guards'] == []
        with pytest.raises(ValueError): await registry.call('create_camera_guard', message='不同需求不得复用请求')
        await asyncio.gather(*list(scenes.compiling.values()))
        saved = scenes.get(first['guardId'], CLIENT)
        revised = await for_chat(ToolRegistry(), scenes, dict(run(), id='guard-chat-002')).call(
            'revise_camera_guard', guard_id=saved['id'], revision=saved['revision'], message='只提醒一次')
        assert revised['guardId'] == saved['id'] and revised['revision'] > saved['revision']
        with pytest.raises(ValueError):
            await registry.call('revise_camera_guard', guard_id=saved['id'], revision=saved['revision'], message='旧版本冲突')
        await asyncio.gather(*list(scenes.compiling.values()))
    asyncio.run(check())


def test_queued_compiler_does_not_deadlock_chat_gate(tmp_path, env):
    async def check():
        scenes = env[0]
        provider = ScriptedProvider([
            tool('create_camera_guard', {'message':'狗进入沙发区域时提醒我'}),
            {'role':'assistant','content':'需求已保存，点卡片继续框选和确认。'}])
        store, runtime = environment(tmp_path, provider)
        runtime.visual_scenes = scenes
        gate = asyncio.Lock()
        @asynccontextmanager
        async def locked_turn(run):
            async with gate: yield provider
        runtime.turn_provider = locked_turn
        async def compile_after_chat(*args, **kwargs):
            async with gate: return dict(plan=PLAN, question='', unsupportedReason='')
        scenes.harness.interpret = AsyncMock(side_effect=compile_after_chat)
        value = runtime.start('狗进入沙发区域时提醒我','main',camera_id='test-device',
            client_id=CLIENT,client_platform='ios',connector_access=True,guard_flow_version=1)
        value = await settle(runtime, value)
        assert value['status'] == 'completed' and value['guardDraftId']
        assert 'draft_visual_skill' not in value['executionContract']['allowed_tools']
        assert 'list_skill_capabilities' not in value['executionContract']['allowed_tools']
        assert store.skills() == [] and value['draft'] is None
        await asyncio.wait_for(asyncio.gather(*list(scenes.compiling.values())), 1)
        saved = scenes.get(value['guardDraftId'],CLIENT)
        assert saved['stage'] == 'select' and saved['status'] == 'draft'
        assert any('新版' in m.get('content','') for m in provider.messages[0] if isinstance(m.get('content'),str))
        await runtime.scheduler.shutdown();store.close()
    asyncio.run(check())


@pytest.mark.parametrize('kwargs', [dict(),dict(client_platform='web',guard_flow_version=1,connector_access=True),
    dict(client_platform='ios',guard_flow_version=1,connector_access=False),
    dict(client_platform='ios',guard_flow_version=1,connector_access=True,execution_mode='history')])
def test_legacy_or_history_do_not_gain_new_mutating_tools(tmp_path,env,kwargs):
    async def check():
        store,runtime=environment(tmp_path,ScriptedProvider([{'role':'assistant','content':'你好'}]))
        runtime.visual_scenes=env[0]
        value=await settle(runtime,runtime.start('你好','compat',client_id=CLIENT,**kwargs))
        assert not value['guardFlowVersion']
        assert 'create_camera_guard' not in value['executionContract']['allowed_tools']
        await runtime.scheduler.shutdown();store.close()
    asyncio.run(check())
