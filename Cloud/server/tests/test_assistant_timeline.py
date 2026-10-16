import json
import time
from uuid import uuid4

import pytest

from fastapi.testclient import TestClient
from evidenceguard.app import create_app
from test_harness import ScriptedProvider


def test_old_message_can_be_opened_and_replied_to_only_in_owners_main_chat(tmp_path):
    provider = ScriptedProvider([dict(role='assistant', content='我会核对原来的观察记录。')])
    app = create_app(tmp_path / 'timeline.sqlite', start_worker=False, provider=provider)
    owner, other = str(uuid4()), str(uuid4())
    with TestClient(app) as api:
        api.headers['X-EG-Installation-ID'] = owner
        assert api.put('/api/personal/conversation', json={'conversationId': 'main'}).status_code == 200
        store = app.state.store
        with store.transaction():
            for index in range(55):
                message = dict(id=f'm-{index}', jobId=f'j-{index}', createdAt=index, title='原消息',
                               body=f'已保存的第 {index} 条观察', why='待核实', sources=[], read=False)
                store.db.execute('INSERT INTO assistant_messages VALUES (?,?,?,?,?)',
                                 (message['id'], owner, message['jobId'], index, json.dumps(message)))
        assert len(app.state.proactive.messages(owner)) == 50
        response = api.get('/api/personal/messages/m-0')
        assert response.status_code == 200 and response.json()['body'] == '已保存的第 0 条观察'
        # Reading the endpoint doesn't mark a hidden or merely prefetched row read.
        assert response.json()['read'] is False
        api.headers['X-EG-Installation-ID'] = other
        assert api.get('/api/personal/messages/m-0').status_code == 404
        assert api.post('/api/personal/messages/m-0/feedback', json={'action': 'read'}).status_code == 404
        api.headers['X-EG-Installation-ID'] = owner
        topic = api.post('/api/agent/conversations', json={'requestId': str(uuid4())}).json()['id']
        body = dict(conversationId=topic, requestId='wrong-topic', message='解释这条消息', replyToMessageId='m-0')
        assert api.post('/api/agent/runs', json=body).status_code == 404
        body.update(conversationId='main', requestId='old-message-reply')
        response = api.post('/api/agent/runs', json=body)
        assert response.status_code == 202
        assert store.run('old-message-reply')['personalContext']['replyToMessage']['id'] == 'm-0'
        assert api.post('/api/personal/messages/m-0/feedback', json={'action': 'read'}).status_code == 200
        assert api.get('/api/personal/messages/m-0').json()['read'] is True


def test_reply_completion_time_is_stable_across_later_saves(tmp_path, monkeypatch):
    app = create_app(tmp_path / 'time.sqlite', start_worker=False, provider=ScriptedProvider([]))
    with TestClient(app):
        store = app.state.store
        run = dict(id='run-time', conversationId='main', createdAt=100, status='running')
        store.save_run(run)
        assert 'completedAt' not in store.run(run['id'])
        monkeypatch.setattr('evidenceguard.store.time.time', lambda: 300)
        run['status'] = 'completed'
        store.save_run(run)
        monkeypatch.setattr('evidenceguard.store.time.time', lambda: 400)
        store.save_run(run)
        assert store.run(run['id'])['completedAt'] == 300


@pytest.mark.parametrize('mode', ['live', 'history'])
def test_main_chat_context_crosses_modes_but_not_topics_or_tool_permissions(tmp_path, mode):
    provider = ScriptedProvider([dict(role='assistant', content='接着之前的记录继续。')])
    app = create_app(tmp_path / 'context.sqlite', start_worker=False, provider=provider)
    owner = str(uuid4())
    with TestClient(app) as api:
        api.headers['X-EG-Installation-ID'] = owner
        api.put('/api/personal/conversation', json={'conversationId': 'main'})
        store = app.state.store
        prior_stream = 'main-history' if mode == 'live' else 'main'
        for index, (stream, client, text) in enumerate([(prior_stream, owner, '接续的原问题'),
                                                       ('separate-topic', owner, '独立话题不要注入'),
                                                       (prior_stream, str(uuid4()), '其他客户端不要注入')]):
            store.save_run(dict(id=f'prior-{index}', conversationId=stream, clientId=client,
                                createdAt=index, status='completed', message=text, text='已有回复', cameraId=None))
        stream = 'main' if mode == 'live' else 'main-history'
        response = api.post('/api/agent/runs', json=dict(conversationId=stream, requestId='continue-main',
                            message='继续解释', executionMode=mode))
        assert response.status_code == 202
        for _ in range(200):
            value = store.run('continue-main')
            if value['status'] not in {'queued', 'running'}: break
            time.sleep(.01)
        assert value['status'] == 'completed'
        turns = [m['content'] for m in provider.messages[0] if m['role'] == 'user']
        assert '接续的原问题' in turns
        assert '独立话题不要注入' not in turns and '其他客户端不要注入' not in turns
        if mode == 'history':
            assert 'request_camera_snapshot' not in value['executionContract']['allowed_tools']
            assert 'draft_visual_skill' not in value['executionContract']['allowed_tools']
