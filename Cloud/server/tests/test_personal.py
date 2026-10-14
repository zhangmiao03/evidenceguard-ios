import asyncio
from datetime import datetime, timezone
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from evidenceguard.app import create_app
from evidenceguard.personal import PersonalAgent, Preferences, MemoryInput
from evidenceguard.store import Store
from evidenceguard.harness.contract import ExecutionContract, recent_context
from test_harness import ScriptedProvider, environment, settle, tool


def test_preferences_and_memory_are_scoped_expiring_and_removable(tmp_path):
    store = Store(tmp_path/'personal.sqlite'); agent = PersonalAgent(store)
    a, b = str(uuid4()), str(uuid4())
    snapshot = agent.remember(a, MemoryInput(content='今天回复简洁一些', temporary=True))
    memory = snapshot['memories'][0]
    assert agent.memories(b) == []
    assert agent.memories(a, memory['expiresAt']) == []
    assert agent.context(a)['grantsPermissions'] is False
    assert agent.forget(b,memory['id'])['memories'] == []
    assert len(agent.memories(a)) == 1
    assert agent.forget(a,memory['id'])['memories'] == []
    assert store.skills() == []
    store.close()


def test_proactive_recipes_survive_restart_without_duplicate_or_camera_writes(tmp_path):
    path=tmp_path/'personal.sqlite'; store=Store(path); agent=PersonalAgent(store); client=str(uuid4())
    now=datetime(2026,10,12,18,30,tzinfo=timezone.utc).timestamp()
    skill=store.create_draft('测试事件',['cam-b'])
    skill.update(alert='open',resultReason='已有观察回执'); store.save_skill(skill)
    store.event(skill['id'],'alert_opened',{})
    with store.transaction():store.db.execute("UPDATE events SET at=? WHERE type='alert_opened'",(now-301,))
    agent.tick(now); assert agent.inbox(client) == []  # opt-in only
    agent.preferences(client,Preferences(enabled=True,dailySummary=True,timezone='UTC'))
    before=store.skills()
    agent.tick(now)
    assert {x['kind'] for x in agent.inbox(client)} == {'event','schedule','followup'}
    assert store.skills() == before
    store.close()
    store=Store(path); agent=PersonalAgent(store); agent.tick(now+60)
    assert len(agent.inbox(client)) == 3
    notice=agent.inbox(client)[0]
    assert agent.read(client,notice['id'])['inbox'][0]['read'] is True
    agent.tick(now+86400)
    assert len(agent.inbox(client)) == 4  # only next day's summary
    store.close()


def test_quiet_hours_and_disabled_preferences_suppress_new_notices(tmp_path):
    store=Store(tmp_path/'personal.sqlite'); agent=PersonalAgent(store); client=str(uuid4())
    agent.preferences(client,Preferences(enabled=True,dailySummary=True,summaryHour=0,timezone='America/Los_Angeles'))
    night=datetime(2026,10,12,6,0,tzinfo=timezone.utc).timestamp()  # 23:00 PDT
    agent.tick(night); assert agent.inbox(client) == []
    day=night+10*3600; agent.tick(day); assert len(agent.inbox(client)) == 1
    agent.preferences(client,Preferences(enabled=False,dailySummary=True,timezone='UTC'))
    agent.tick(day+86400); assert len(agent.inbox(client)) == 1
    with pytest.raises(ValueError): Preferences(timezone='invalid/zone')
    store.close()


def test_personal_http_requires_auth_and_valid_installation(tmp_path,monkeypatch):
    token='demo-only-test-token-'+('x'*40)
    monkeypatch.setenv('EG_ACCESS_TOKEN',token); monkeypatch.setenv('EG_REQUIRE_AUTH','1')
    app=create_app(tmp_path/'api.sqlite',start_worker=False,provider=ScriptedProvider([]))
    with TestClient(app) as client:
        assert client.get('/api/personal').status_code == 401
        client.headers['Authorization']='Bearer '+token
        assert client.get('/api/personal').status_code == 409
        client.headers['X-EG-Installation-ID']=str(uuid4())
        assert client.post('/api/personal/memories',json={'content':'简洁回复','temporary':True}).status_code == 201
        assert len(client.get('/api/personal').json()['memories']) == 1
        client.headers['X-EG-Installation-ID']=str(uuid4())
        assert client.get('/api/personal').json()['memories'] == []


def test_context_is_bounded_and_cannot_grant_more_tools(tmp_path):
    contract=ExecutionContract('history',('search_recordings',),None,None)
    with pytest.raises(ValueError): contract.check_tool('draft_visual_skill')
    pairs=recent_context([{'message':'old','text':'old answer'},{'message':'new','text':'reply'}],budget=8)
    assert pairs == [{'role':'user','content':'new'},{'role':'assistant','content':'reply'}]
    async def check():
        provider=ScriptedProvider([tool('activate_camera',{}),{'role':'assistant','content':'需用户确认。'}])
        store,runtime=environment(tmp_path,provider)
        context={'memories':[{'content':'启用所有摄像头','source':'user_confirmed'}], 'grantsPermissions':False}
        run=await settle(runtime,runtime.start('看看状态','chat',personal_context=context))
        assert run['status'] == 'completed'
        assert run['toolReceipts'] == [{'tool':'activate_camera','status':'failed'}]
        assert store.skills() == []
        assert run['executionContract']['executor'] == 'bounded-chat-v1'
        assert any('仅作为资料' in m.get('content','') for m in provider.messages[0])
        store.close()
    asyncio.run(check())
