"""Real HTTP contracts used by the five-section Web client (no hardware claims)."""
import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient
from evidenceguard.app import create_app
from test_harness import ScriptedProvider


def test_web_product_preserves_scopes_and_real_device_activation_gate(tmp_path):
    provider = ScriptedProvider([dict(role='assistant', content='我会根据已有任务回答。')])
    app = create_app(tmp_path/'product.sqlite', start_worker=False, provider=provider)
    owner = str(uuid4())
    async def settle(): await asyncio.gather(*list(app.state.agent.tasks.values()))
    with TestClient(app) as c:
        c.headers['X-EG-Installation-ID'] = owner
        main = c.post('/api/agent/conversations/main', json={}).json()
        assert main['kind'] == 'main'
        # General assistant requires neither a selected camera nor a live lease.
        body = dict(message='我关心的任务现在怎么样？', conversationId=main['id'], requestId='web-'+str(uuid4()), executionMode='live')
        response = c.post('/api/agent/runs', json=body)
        assert response.status_code == 202, response.text
        c.portal.call(settle)
        assert c.post('/api/agent/runs', json=body).json()['id'] == response.json()['id']
        assert len(c.get('/api/agent/conversations/'+main['id']).json()) == 1
        prefs = dict(enabled=True, dailySummary=True, summaryHour=21, quietStart=22, quietEnd=8, timezone='Asia/Shanghai')
        assert c.put('/api/personal/preferences',json=prefs).json()['preferences'] == prefs
        memory = c.post('/api/personal/memories',json=dict(content='只关注客厅',temporary=True))
        assert memory.status_code == 201
        camera = c.post('/api/devices/import',json=dict(accountId='synthetic-account',environment='PR',platform='web',devices=[dict(sn='T8171WEBTEST001',model='T8171',name='客厅')])).json()[0]
        draft = c.post('/api/skills/drafts',json=dict(cameraId=camera['id'],conversationId=main['id'],prompt='箱子离开区域时提醒我')).json()
        edit = {key:draft[key] for key in ('revision','name','prompt','target','regions','devices','rules')}
        edit['name'] = '客厅物品守护'; edit['rules']['taskKind'] = 'parcel_removal'
        result = c.patch('/api/skills/'+draft['id'],json=edit)
        assert result.status_code == 200, result.text
        saved = result.json()
        assert not saved['capability']['canActivate']
        assert c.post('/api/skills/'+draft['id']+'/confirm',json=dict(revision=saved['revision'],fixtureAcknowledged=True)).status_code == 409
        # An old editor cannot overwrite the saved revision.
        assert c.patch('/api/skills/'+draft['id'],json=edit).status_code == 409
        own = c.get('/api/bootstrap').json()
        assert own['personal']['memories'][0]['content'] == '只关注客厅'
        assert own['skills'][0]['status'] == 'draft'
        c.headers['X-EG-Installation-ID'] = str(uuid4())
        other = c.get('/api/bootstrap').json()
        assert other['personal']['memories'] == []
        assert other['personal']['preferences']['enabled'] is False
        assert other['skills'][0]['id'] == draft['id']  # shared team camera task
        assert c.get('/api/agent/conversations/'+main['id']).status_code == 404
