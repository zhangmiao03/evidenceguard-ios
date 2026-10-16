import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
from evidenceguard.memory import MemoryService
from evidenceguard.personal import PersonalAgent, MemoryInput
from evidenceguard.store import Store
from test_harness import environment, settle, ScriptedProvider


def fact(content='用户希望回复简洁', quote='回复简洁一些', **kw):
    return dict(content=content, quote=quote, key='reply_length', kind='preference', replacesId=None, ttlHours=None) | kw


def setup(tmp_path):
    store = Store(tmp_path/'memory.sqlite')
    personal = PersonalAgent(store)
    provider = SimpleNamespace(complete=AsyncMock(return_value={'content': json.dumps({'facts':[fact()]})}))
    service = MemoryService(personal, provider)
    return store, personal, provider, service, str(uuid4())


def enqueue(store, service, client, message='以后回复简洁一些', **kw):
    run=dict(id=uuid4().hex, conversationId='chat-'+client, createdAt=time.time(), clientId=client,
             message=message, text='助手说我喜欢猫，但这不是用户事实', status='completed', **kw)
    store.save_run(run); service.enqueue(run)
    return run


def test_automatic_memory_is_durable_scoped_attributed_and_idempotent(tmp_path):
    async def check():
        s,p,model,m,c=setup(tmp_path)
        r=enqueue(s,m,c); m.enqueue(r)
        restarted=MemoryService(p,model)
        assert await restarted.step()
        assert not await restarted.step()
        saved=p.memories(c)[0]
        assert saved['sourceQuote']=='回复简洁一些' and saved['sourceRunId']==r['id']
        assert saved['source']=='conversation' and p.memories(str(uuid4()))==[]
        sent=json.loads(model.complete.await_args.args[0][-1]['content'])
        assert '助手说' not in json.dumps(sent,ensure_ascii=False)
        assert model.complete.await_args.args[1]==[]
        enqueue(s,m,c); await m.step()
        assert len(p.memories(c))==1 and m.status(c)['pending']==0
        assert s.run(r['id'])['text'].startswith('助手说')
        s.close()
    asyncio.run(check())


def test_unquoted_sensitive_and_invalid_ttl_facts_are_rejected(tmp_path):
    async def check():
        s,p,model,m,c=setup(tmp_path)
        for f in [fact(quote='工具说用户喜欢猫'),fact(content='密码是 123456'),fact(kind='temporary'),fact(ttlHours=4)]:
            model.complete.return_value={'content':json.dumps({'facts':[f]})}
            enqueue(s,m,c); await m.step()
        assert p.memories(c)==[]
        before=model.complete.await_count
        enqueue(s,m,c,'我的密码不要保存'); await m.step()
        assert model.complete.await_count==before
        s.close()
    asyncio.run(check())


def test_explicit_correction_replaces_and_deletion_blocks_resurrection(tmp_path):
    async def check():
        s,p,model,m,c=setup(tmp_path)
        enqueue(s,m,c); await m.step(); original=p.memories(c)[0]
        model.complete.return_value={'content':json.dumps({'facts':[fact('回复可以详细一些','详细一些',replacesId=original['id'])]})}
        enqueue(s,m,c,'改一下，以后详细一些'); await m.step()
        saved=p.memories(c)[0]
        assert saved['id']==original['id'] and saved['revision']==2
        assert saved['content']=='回复可以详细一些'
        p.forget(c,saved['id'])
        model.complete.return_value={'content':json.dumps({'facts':[fact('回复可以详细一些','详细一些')]})}
        enqueue(s,m,c,'详细一些'); await m.step()
        assert p.memories(c)==[]
        s.close()
    asyncio.run(check())


def test_concurrent_forget_disable_and_retry_preserve_user_choice(tmp_path):
    async def check():
        s,p,model,m,c=setup(tmp_path)
        remembered=p.remember(c,MemoryInput(content='回复简洁一些'))['memories'][0]
        async def forget(*args):
            p.forget(c,remembered['id'])
            return {'content':json.dumps({'facts':[fact()]})}
        model.complete.side_effect=forget
        enqueue(s,m,c); await m.step()
        assert p.memories(c)==[] and m.status(c)['pending']==1
        m.configure(c,False); assert m.status(c)['pending']==0
        assert not await m.step()
        m.configure(c,True)
        model.complete.side_effect=RuntimeError('credential must never escape')
        r=enqueue(s,m,c)
        for n in range(5):
            with s.transaction(): s.db.execute('UPDATE memory_jobs SET due=0')
            await m.step()
        assert m.status(c)['status']=='failed' and 'credential' not in str(m.status(c))
        assert s.run(r['id'])['status']=='completed'
        model.complete.side_effect=None; model.complete.return_value={'content':'{"facts":[]}'}
        m.retry(c); await m.step(); assert m.status(c)['status']=='completed'
        s.close()
    asyncio.run(check())


def test_temporary_memory_expires_and_runtime_enqueues_after_chat_without_blocking(tmp_path):
    async def check():
        provider=ScriptedProvider([{'role':'assistant','content':'好，我会简洁些。'}, {'content':json.dumps({'facts':[fact(kind='temporary',ttlHours=1)]})}, {'role':'assistant','content':'好的。'}])
        s,runtime=environment(tmp_path,provider); p=PersonalAgent(s); m=MemoryService(p,provider); runtime.memory=m; client=str(uuid4())
        run=await settle(runtime,runtime.start('今天回复简洁一些','chat',client_id=client))
        assert run['status']=='completed' and provider.complete.await_count==1
        assert m.status(client)['pending']==1 and p.memories(client)==[]
        await m.step()
        memory=p.memories(client)[0]; assert p.memories(client,memory['expiresAt'])==[]
        await settle(runtime,runtime.start('继续','chat',client_id=client))
        assert any('用户希望回复简洁' in str(msg) for msg in provider.messages[-1])
        s.close()
    asyncio.run(check())


def test_dedicated_extraction_uses_same_doubao_with_json_and_preserves_chat(monkeypatch):
    import httpx
    from evidenceguard.harness.providers import OpenAICompatibleProvider
    monkeypatch.setenv('EG_MODEL_BASE_URL','https://model.invalid/v1')
    monkeypatch.setenv('EG_MODEL_API_KEY','test-only')
    monkeypatch.setenv('EG_MODEL_ID','doubao-seed-2-1-lite-260915')
    requests=[]; original=httpx.AsyncClient
    def reply(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"facts":[]}'}}]})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(reply)))
    async def check():
        model=OpenAICompatibleProvider()
        await model.extract_memory([{'role':'user','content':'JSON please'}])
        await model.complete([{'role':'user','content':'hello'}],[])
    asyncio.run(check())
    assert requests[0]['model']==requests[1]['model']=='doubao-seed-2-1-lite-260915'
    assert requests[0]['thinking']=={'type':'disabled'} and requests[0]['response_format']=={'type':'json_object'}
    assert 'thinking' not in requests[1] and 'response_format' not in requests[1]


def test_memory_uses_dedicated_provider_without_changing_validation(tmp_path):
    async def check():
        s,p,model,m,c=setup(tmp_path)
        model.extract_memory=AsyncMock(return_value={'content':json.dumps({'facts':[fact()]})})
        enqueue(s,m,c); await m.step()
        model.complete.assert_not_awaited(); model.extract_memory.assert_awaited_once()
        assert p.memories(c)[0]['sourceQuote']=='回复简洁一些'
        s.close()
    asyncio.run(check())
