import asyncio
from uuid import uuid4

from fastapi.testclient import TestClient
from evidenceguard.app import create_app
from test_harness import ScriptedProvider


def create(client, request=None):
    response = client.post('/api/agent/conversations', json={'requestId':str(request or uuid4())})
    assert response.status_code == 201, response.text
    return response.json()


def headers(): return {'X-EG-Installation-ID':str(uuid4())}


def test_topics_are_durable_idempotent_and_do_not_rebind_main(tmp_path):
    path = tmp_path/'chat.sqlite'; owner = headers(); request = uuid4()
    with TestClient(create_app(path,start_worker=False,provider=ScriptedProvider([]))) as c:
        c.headers.update(owner)
        assert c.put('/api/personal/conversation',json={'conversationId':'main'}).status_code==200
        topic = create(c,request)
        assert create(c,request)['id']==topic['id']
        assert len(c.get('/api/agent/conversations').json())==2
        assert c.put('/api/personal/conversation',json={'conversationId':topic['id']}).status_code==409
        assert c.put('/api/personal/conversation',json={'conversationId':'another-main'}).status_code==409
        assert c.patch('/api/agent/conversations/'+topic['id'],json={'title':'门口包裹'}).status_code==200
    with TestClient(create_app(path,start_worker=False,provider=ScriptedProvider([]))) as c:
        c.headers.update(owner)
        items=c.get('/api/agent/conversations').json()
        assert items[0]['id']=='main' and items[0]['kind']=='main'
        assert items[1]['id']==topic['id'] and items[1]['title']=='门口包裹'


def test_topic_and_its_history_stream_are_installation_scoped(tmp_path):
    with TestClient(create_app(tmp_path/'chat.sqlite',start_worker=False,provider=ScriptedProvider([]))) as c:
        c.headers.update(headers()); topic=create(c); request=str(uuid4())
        c.headers.update(headers())
        assert c.get('/api/agent/conversations').json()==[]
        for key in (topic['id'],topic['id']+'-history'):
            assert c.get('/api/agent/conversations/'+key).status_code==404
            assert c.post('/api/agent/runs',json=dict(conversationId=key,requestId=request,message='读旧记录')).status_code==404
        assert c.patch('/api/agent/conversations/'+topic['id'],json={'title':'窃取'}).status_code==404
        assert c.get('/api/agent/conversations/topic-not-created').status_code==404
        del c.headers['X-EG-Installation-ID']
        assert c.get('/api/agent/conversations/'+topic['id']).status_code==404


def test_new_topic_does_not_inherit_transcript_but_keeps_confirmed_memory(tmp_path):
    p=ScriptedProvider([dict(role='assistant',content='这是旧话题的独有回答。'),dict(role='assistant',content='这是新话题。')])
    app=create_app(tmp_path/'chat.sqlite',start_worker=False,provider=p)
    async def settle(): await asyncio.gather(*list(app.state.agent.tasks.values()))
    with TestClient(app) as c:
        c.headers.update(headers())
        c.put('/api/personal/conversation',json={'conversationId':'main'})
        assert c.post('/api/personal/memories',json={'content':'我只关注门口的包裹','temporary':False}).status_code==201
        first=create(c); second=create(c)
        for topic,message in ((first,'旧话题专属暗号甲'),(second,'你好，新话题')):
            response=c.post('/api/agent/runs',json=dict(conversationId=topic['id'],requestId=str(uuid4()),message=message))
            assert response.status_code==202, response.text
            c.portal.call(settle)
        second_context=str(p.messages[-1])
        assert '旧话题专属暗号甲' not in second_context and '旧话题的独有回答' not in second_context
        assert '我只关注门口的包裹' in second_context
        assert len(c.get('/api/agent/conversations/'+first['id']).json())==1
        assert len(c.get('/api/agent/conversations/'+second['id']).json())==1
        summaries=c.get('/api/agent/conversations').json()
        assert summaries[1]['title']=='你好，新话题'
        assert summaries[1]['preview']=='这是新话题。'
        assert not summaries[1]['hasActiveRun']
        assert app.state.proactive.owner('main')==c.headers['X-EG-Installation-ID']


def test_history_scope_shares_navigation_but_not_live_transcript(tmp_path):
    p=ScriptedProvider([dict(role='assistant',content='只读资料回答')])
    app=create_app(tmp_path/'chat.sqlite',start_worker=False,provider=p)
    async def settle(): await asyncio.gather(*list(app.state.agent.tasks.values()))
    with TestClient(app) as c:
        c.headers.update(headers()); topic=create(c)
        response=c.post('/api/agent/runs',json=dict(conversationId=topic['id']+'-history',executionMode='history',requestId=str(uuid4()),message='回顾过去'))
        assert response.status_code==202
        c.portal.call(settle)
        assert c.get('/api/agent/conversations/'+topic['id']).json()==[]
        index=c.get('/api/agent/conversations').json()
        assert len(index)==1 and index[0]['lastMode']=='history' and index[0]['title']=='回顾过去'
        assert set(response.json()['executionContract']['allowed_tools'])=={'search_evidence','read_stored_image','search_recordings'}


def test_main_history_cannot_be_read_or_rebound_by_other_installation(tmp_path):
    with TestClient(create_app(tmp_path/'chat.sqlite',start_worker=False,provider=ScriptedProvider([]))) as c:
        c.headers.update(headers()); c.put('/api/personal/conversation',json={'conversationId':'old-main'})
        c.headers.update(headers())
        assert c.get('/api/agent/conversations/old-main-history').status_code==404
        assert c.put('/api/personal/conversation',json={'conversationId':'old-main-history'}).status_code==409
