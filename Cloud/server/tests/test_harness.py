import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from evidenceguard.camera.registry import CameraRegistry
from evidenceguard.camera.adapters.eufy_ports import EufyT8171Adapter
from evidenceguard.harness.runtime import AgentRuntime
from evidenceguard.harness.tools import ToolRegistry, build_tools
from evidenceguard.store import Store


class ScriptedProvider:
    name = 'test-provider'
    ready = True

    def __init__(self, answers):
        self.answers = iter(answers)
        self.messages = []
        def answer(messages, tools):
            self.messages.append(json.loads(json.dumps(messages)))
            return next(self.answers)
        self.complete = AsyncMock(side_effect=answer)


def tool(name, args):
    return {'role': 'assistant', 'content': None, 'tool_calls': [
        {'id': 'call-' + name, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}]}


def environment(tmp_path, provider):
    store = Store(tmp_path / 'harness.sqlite3')
    cameras = CameraRegistry(EufyT8171Adapter())
    return store, AgentRuntime(store, build_tools(store, cameras), provider, cameras)


async def settle(runtime, run):
    await asyncio.wait_for(asyncio.gather(*list(runtime.tasks.values())), timeout=3)
    return runtime.store.run(run['id'])


def test_registry_rejects_duplicate_tools():
    registry = ToolRegistry()
    registry.register('x', AsyncMock())
    with pytest.raises(ValueError):
        registry.register('x', AsyncMock())


def test_query_does_not_create_or_activate_skill(tmp_path):
    async def check():
        provider = ScriptedProvider([tool('list_tasks', {}), {'role': 'assistant', 'content': '还没有任务。'}])
        store, runtime = environment(tmp_path, provider)
        run = await settle(runtime, runtime.start('现在怎么样', 'chat', request_id='query'))
        assert run['status'] == 'completed'
        assert store.skills() == []
        assert run['draft'] is None
        assert run['toolReceipts'] == [{'tool': 'list_tasks', 'status': 'completed'}]
        assert provider.messages[-1][-1]['role'] == 'tool'
        store.close()
    asyncio.run(check())


def test_official_empty_camera_receipt_blocks_unavailable_workflow_claims(tmp_path,monkeypatch):
    from evidenceguard.app import create_app
    monkeypatch.setenv('EG_CAMERA_SOURCE','official_sdk')
    async def check():
        provider=ScriptedProvider([tool('list_camera_capabilities',{}),
            {'role':'assistant','content':'已经开始看门口了，你还可以选录像试跑。'},
            {'role':'assistant','content':'嗨，我在。'}])
        app=create_app(tmp_path/'official-empty.sqlite3',start_worker=False,provider=provider)
        try:
            runtime=app.state.agent
            run=await settle(runtime,runtime.start('帮我看住门口包裹','guard'))
            assert run['status']=='completed' and run['cameraUnavailable']
            assert '连接摄像头' in run['text'] and '开始看门口' not in run['text'] and '录像试跑' not in run['text']
            assert run['draft'] is None and app.state.store.skills()==[]
            events=await app.state.tools.call('list_camera_events')
            assert events['registeredDeviceCount']==0 and events['events']==[]
            greeting=await settle(runtime,runtime.start('你好','greeting'))
            assert greeting['text']=='嗨，我在。' and greeting['toolReceipts']==[]
        finally:
            await app.state.agent.scheduler.shutdown();await app.state.push.provider.close()
            await app.state.videos.shutdown();app.state.store.close()
    asyncio.run(check())


def test_created_skill_remains_draft_and_events_replay(tmp_path):
    async def check():
        provider = ScriptedProvider([tool('draft_visual_skill', {
            'prompt': '看住测试箱子', 'devices': ['cam-a'], 'name': '测试箱子',
            'target_description': '测试标记物', 'rules': {},
        }), {'role': 'assistant', 'content': '请检查草案。'}])
        store, runtime = environment(tmp_path, provider)
        run = await settle(runtime, runtime.start('看住测试箱子', 'chat', request_id='create'))
        assert run['status'] == 'completed'
        assert store.skill(run['draft']['id'])['status'] == 'draft'
        events = store.events(run['id'])
        assert [e['sequence'] for e in events] == list(range(1, len(events) + 1))
        assert store.events(run['id'], after=2) == events[2:]
        assert events[-1]['type'] == 'response_completed'
        store.close()
    asyncio.run(check())


def test_missing_provider_configuration_makes_zero_model_calls(tmp_path):
    async def check():
        provider = ScriptedProvider([]); provider.ready = False
        store, runtime = environment(tmp_path, provider)
        run = await settle(runtime, runtime.start('看住箱子', 'chat'))
        assert run['status'] == 'failed'
        provider.complete.assert_not_called()
        assert store.skills() == []
        store.close()
    asyncio.run(check())


def test_cancel_and_duplicate_request_do_not_duplicate_work(tmp_path):
    async def check():
        entered, gate = asyncio.Event(), asyncio.Event()
        provider = ScriptedProvider([])
        async def blocked(*args):
            entered.set(); await gate.wait()
        provider.complete.side_effect = blocked
        store, runtime = environment(tmp_path, provider)
        run = runtime.start('状态查询', 'chat', request_id='same')
        await asyncio.wait_for(entered.wait(), timeout=3)
        assert runtime.start('状态查询', 'chat', request_id='same')['id'] == run['id']
        with pytest.raises(ValueError): runtime.start('不同的输入', 'chat', request_id='same')
        cancelled = await runtime.cancel(run['id'])
        assert cancelled['status'] == 'cancelled'
        provider.complete.assert_called_once()
        assert store.events(run['id'])[-1]['type'] == 'run_cancelled'
        assert store.skills() == []
        store.close()
    asyncio.run(check())


def test_restart_marks_incomplete_run_interrupted(tmp_path):
    provider = ScriptedProvider([])
    store, runtime = environment(tmp_path, provider)
    store.save_run(dict(id='unfinished', conversationId='chat', createdAt=1, status='running'))
    resumed = AgentRuntime(store, runtime.tools, provider)
    assert store.run('unfinished')['status'] == 'interrupted'
    assert store.events('unfinished')[-1]['type'] == 'run_interrupted'
    assert resumed.tasks == {}
    store.close()


def test_task_context_cannot_be_switched_by_model_or_request_id(tmp_path):
    async def check():
        provider = ScriptedProvider([])
        store, runtime = environment(tmp_path, provider)
        a = store.create_draft('第一个任务', ['cam-a'])
        b = store.create_draft('第二个任务', ['cam-b'])
        with pytest.raises(ValueError): runtime.start('看看现场','chat',skill_id=a['id'],camera_id='cam-b')
        provider.answers=iter([{'role':'assistant','content':'查询完成'}])
        run=await settle(runtime,runtime.start('查询','chat',skill_id=a['id'],request_id='id'))
        assert run['cameraId']=='cam-a'
        with pytest.raises(ValueError): runtime.start('查询','chat',skill_id=b['id'],request_id='id')
        with pytest.raises(ValueError): runtime.start('新查询','chat',skill_id=b['id'])
        store.close()
    asyncio.run(check())


def test_model_snapshot_request_produces_visible_receipt_and_image_message(tmp_path,monkeypatch):
    async def check():
        from evidenceguard.camera.service import CameraService
        from evidenceguard.harness.scheduler import TaskScheduler
        from evidenceguard.camera.contracts import DeviceManifest, CapabilityState, FrameRef, SnapshotKind, SnapshotReceipt
        import time
        monkeypatch.setenv('EG_MODEL_VISION','1')
        provider=ScriptedProvider([tool('request_camera_snapshot',{}),{'role':'assistant','content':'收到测试画面。'}])
        store=Store(tmp_path/'camera-run.sqlite')
        scheduler=TaskScheduler()
        cameras=AsyncMock()
        cameras.manifests.return_value=[DeviceManifest('cam-a','T8171','测试','primary','online','fixture',(),{'liveSnapshot':CapabilityState.SUPPORTED},'test')]
        now=time.time()
        cameras.snapshot.side_effect=lambda *args: SnapshotReceipt('request','completed',SnapshotKind.LIVE,FrameRef('cam-a-1-1','cam-a','main',time.time(),time.time(),'fixture','live','v1'),'新画面')
        cameras.frame_bytes.return_value=(b'fixture-image','image/jpeg')
        service=CameraService(store,cameras,scheduler)
        runtime=AgentRuntime(store,build_tools(store,cameras,service),provider,cameras,scheduler)
        run=await settle(runtime,runtime.start('看看现在的画面','camera-chat',camera_id='cam-a'))
        assert run['status']=='completed'
        assert run['captures'][0]['cameraId']=='cam-a'
        assert run['captures'][0]['imageUrl'].startswith('/api/media/')
        last=provider.messages[-1][-1]
        assert last['role']=='user' and any(x['type']=='image_url' for x in last['content'])
        assert store.skills()==[]
        await scheduler.shutdown(); store.close()
    asyncio.run(check())
