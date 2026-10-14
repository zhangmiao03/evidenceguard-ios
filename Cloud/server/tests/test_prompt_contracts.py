"""Check emitted model requests and receipts, without pretending to test model accuracy."""
import asyncio
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from evidenceguard.store import Store
from evidenceguard.video.providers import LiteVideoProvider
from evidenceguard.visual_review import VisualReview
from test_harness import ScriptedProvider, environment, settle, tool


@pytest.mark.parametrize('mode', ['live', 'history'])
def test_chat_and_proactive_receive_current_product_guidance(tmp_path, mode):
    async def check():
        provider = ScriptedProvider([
            dict(role='assistant', content='请打开任务中的草案。'),
            tool('read_proactive_context', {}),
            dict(role='assistant', content=json.dumps(dict(valueScore=0, reason='没有新依据', sourceIds=[]))),
        ])
        store, runtime = environment(tmp_path, provider)
        run = await settle(runtime, runtime.start('Web 在哪里编辑和设置提醒？', 'chat', execution_mode=mode))
        assert run['status'] == 'completed'
        await runtime.proactive('proactive-test', dict(clientId='test-client', sources=[]))
        # Both request paths need current UI instructions, not only a shared constant in source.
        for messages in (provider.messages[0], provider.messages[1]):
            system = messages[0]['content']
            for entry in ('助手 / 摄像头 Skill / 任务 / 记忆 / 设置', '继续设置守护', '对象 / 条件 / 确认', '保存提醒设置'):
                assert entry in system
            assert 'APNs' in system and 'Web Push' in system
            assert 'Web 设备工作台当前只提供' not in system
        tools = {item['function']['name'] for item in provider.complete.call_args_list[1].args[1]}
        assert tools == {'read_proactive_context', 'read_observation_image'}
        assert store.skills() == []
        if mode == 'history':
            assert set(run['executionContract']['allowed_tools']) == {'search_evidence', 'read_stored_image', 'list_camera_events'}
        await runtime.scheduler.shutdown()
        store.close()
    asyncio.run(check())


@pytest.mark.parametrize('kind', ['parcel_removal', 'marker_region', 'pet_activity'])
def test_draft_receipt_links_both_clients_without_activating(tmp_path, kind):
    async def check():
        provider = ScriptedProvider([
            tool('draft_visual_skill', dict(prompt='测试守护需求', devices=['cam-a'], name='待确认守护',
                 target_description='测试对象', rules=dict(taskKind=kind))),
            dict(role='assistant', content='请只到旧 App 编辑，Web 没有这个功能。'),
        ])
        store, runtime = environment(tmp_path, provider)
        run = await settle(runtime, runtime.start('创建草案', 'chat'))
        # The server's capability-backed receipt replaces misleading generated instructions.
        assert run['status'] == 'completed'
        assert 'iOS 或 Web' in run['text'] and '继续设置守护' in run['text']
        assert 'Web 没有' not in run['text'] and '尚未启用' in run['text']
        assert store.skill(run['draft']['id'])['status'] == 'draft'
        assert store.owner('cam-a') is None
        await runtime.scheduler.shutdown()
        store.close()
    asyncio.run(check())


def test_image_review_request_does_not_assume_event_thumbnail_origin(monkeypatch):
    monkeypatch.setenv('EG_VIDEO_BASE_URL', 'https://vision.invalid/v1')
    monkeypatch.setenv('EG_VIDEO_MODEL_ID', 'test-vision')
    monkeypatch.setenv('EG_VIDEO_API_KEY', 'test-key')
    sent = []
    def respond(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=dict(choices=[dict(message=dict(content=json.dumps(
            dict(visible='可见测试物体', uncertainties='设备拍摄时间未知'))))]))
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(respond)))
    result = asyncio.run(LiteVideoProvider().describe_observations([(b'test-sample', 'image/jpeg', None)]))
    assert result['visible'] == '可见测试物体'
    content = sent[0]['messages'][1]['content']
    instructions = content[0]['text']
    assert '客户端直播取样' in instructions and '合成测试' in instructions
    assert '不保证是设备拍摄时间' in instructions
    assert '来源记录时间：未知' in content[1]['text']
    assert content[2]['type'] == 'image_url'


def test_updated_visual_prompt_does_not_reuse_old_cache(tmp_path):
    async def check():
        store = Store(tmp_path/'visual.sqlite')
        provider = SimpleNamespace(ready=True, model='test', base='test',
            describe_observations=AsyncMock(return_value=dict(visible='新核验', uncertainties='离散取样')))
        visual = VisualReview(store, provider)
        media = store.save_media(dict(device_id='sdk-test', frame_id='sample'), b'test-sample', 'image/jpeg')
        sources = [(media['id'], None)]
        legacy = hashlib.sha256(json.dumps(['sdk-test', 'episode', sources, 'test', 'test', 'visual-review-v1'], sort_keys=True).encode()).hexdigest()
        with store.transaction():
            store.db.execute('INSERT INTO visual_cache VALUES (?,?)', (legacy, json.dumps(dict(status='completed', review={'visible':'旧提示词结果'}))))
        first = await visual.review('sdk-test', 'episode', sources)
        assert first['review']['visible'] == '新核验' and first['cached'] is False
        assert (await visual.review('sdk-test', 'episode', sources))['cached'] is True
        assert provider.describe_observations.await_count == 1
        assert visual.usage('sdk-test')['requests'] == 1
        store.close()
    asyncio.run(check())
