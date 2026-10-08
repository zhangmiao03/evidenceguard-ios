import asyncio,json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from evidenceguard.app import create_app
from evidenceguard.camera.contracts import DeviceManifest
from test_harness import ScriptedProvider,environment,settle

def test_manual_editor_entry_creates_unapproved_camera_bound_draft(tmp_path,monkeypatch):
    monkeypatch.setenv('EG_VIDEO_ROOT',str(tmp_path/'videos'))
    app=create_app(tmp_path/'db',start_worker=False,provider=SimpleNamespace(name='off',ready=False))
    app.state.camera.active.manifests=AsyncMock(return_value=[DeviceManifest('cam-a','T8171','屋檐','primary','online','fixture-lab',(),{},'test')])
    store=app.state.store
    active=store.create_draft('已有任务',['cam-a']);store.confirm(active['id'],1)
    old=store.create_draft('过去的录像',['cam-a']);old.update(status='completed',replay={'recordingId':'old-video'});store.save_skill(old)
    with TestClient(app) as client:
        before=store.skill(active['id'])
        reply=client.post('/api/skills/drafts',json=dict(cameraId='cam-a',conversationId='chat-a',prompt='看住箱子',replacesId=old['id']))
        assert reply.status_code==201
        s=reply.json()
        assert s['status']=='draft' and s['originConversationId']=='chat-a' and s['devices']==['cam-a']
        assert not s.get('replay') and s['rules']['taskKind']=='unspecified'
        assert not s['capability']['canActivate'] and store.skill(active['id'])==before
        assert client.post('/api/skills/drafts',json=dict(cameraId='cam-unknown',conversationId='chat-a')).status_code==409
        assert client.post(f'/api/skills/{s["id"]}/confirm',json={'revision':1}).status_code==409

def test_assistant_receives_current_state_instead_of_old_draft_snapshot(tmp_path):
    async def check():
        provider=ScriptedProvider([{'role':'assistant','content':'旧任务已完成，需要新建草案。'}])
        store,runtime=environment(tmp_path,provider)
        old=store.create_draft('旧任务',['cam-a'])
        store.save_run(dict(id='old-run',conversationId='chat',skillId=None,executionMode='live',status='completed',message='创建草案',text='草案待确认',draft=old,createdAt=0))
        old.update(status='completed');store.save_skill(old)
        manual=store.create_draft('新的手动草案',['cam-a']);manual['originConversationId']='chat';store.save_skill(manual)
        await settle(runtime,runtime.start('继续看住它','chat'))
        current=next(m['content'] for m in provider.messages[0] if m['role']=='system' and m['content'].startswith('服务器当前任务事实'))
        assert old['id'] in current and '"status": "completed"' in current
        assert manual['id'] in current and '保存绝不等于启用' in current
        store.close()
    asyncio.run(check())
