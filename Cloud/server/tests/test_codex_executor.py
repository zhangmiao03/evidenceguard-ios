"""Exercise the real stdio transport against a deterministic fake App Server."""
import asyncio
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from evidenceguard.harness.codex import CodexTurn, EXECUTOR, structured_text
from evidenceguard.harness.providers import ProviderError


@pytest.fixture
def server(tmp_path):
    if os.name != 'posix':
        pytest.skip('Linux cloud executor uses POSIX process groups and an executable shebang; run this transport suite on Linux')
    capture=tmp_path/'wire.jsonl'
    script=tmp_path/'app-server'
    script.write_text('#!'+sys.executable+'\n'+'''import json, os, sys, time
capture = '''+repr(str(capture))+'''
def emit(x): print(json.dumps(x),flush=True)
def record(x):
 with open(capture,'a') as f: f.write(json.dumps(x)+'\\n')
record({'argv':sys.argv,'env':dict(os.environ)})
mode=''; count=0
for line in sys.stdin:
 v=json.loads(line); record(v); m=v.get('method'); rid=v.get('id')
 if m=='initialize':emit({'id':rid,'result':{}})
 elif m=='thread/start':emit({'id':rid,'result':{'thread':{'id':'thread-test'}}})
 elif m=='thread/inject_items':emit({'id':rid,'result':{}})
 elif m=='turn/start':
  mode=v['params']['input'][0]['text']
  if mode=='stall':time.sleep(60)
  # The protocol allows requests/notifications before the turn/start reply.
  if mode=='foreign':
   emit({'id':77,'method':'item/tool/call','params':{'threadId':'wrong','turnId':'turn-test','callId':'c1','tool':'list_tasks','arguments':{}}})
  elif mode=='unknown':
   emit({'id':77,'method':'item/tool/call','params':{'threadId':'thread-test','turnId':'turn-test','callId':'c1','tool':'delete_everything','arguments':{}}})
  elif mode=='native':emit({'id':77,'method':'item/commandExecution/requestApproval','params':{}})
  elif mode=='fail':
   emit({'method':'item/completed','params':{'item':{'type':'agentMessage','text':'partial unverified'}}})
   emit({'method':'turn/completed','params':{'turn':{'status':'failed','error':'secret-sentinel'}}})
  elif mode=='malformed': print('{invalid',flush=True)
  elif mode=='eof':sys.exit(0)
  else:
   emit({'id':77,'method':'item/tool/call','params':{'threadId':'thread-test','turnId':'turn-test','callId':'c1','tool':'list_tasks','arguments':{}}})
  emit({'id':rid,'result':{'turn':{'id':'turn-test'}}})
 elif rid==77 and 'result' in v:
  emit({'method':'item/completed','params':{'item':{'type':'agentMessage','text':'checking','phase':'commentary'}}})
  emit({'method':'item/completed','params':{'item':{'type':'agentMessage','text':'任务已查到，尚未启用。','phase':'final_answer'}}})
  emit({'method':'turn/completed','params':{'turn':{'status':'completed'}}})
''')
    script.chmod(0o755)
    return script,capture,tmp_path/'runs'


def turn_for(server):
    binary,_,root=server
    provider=SimpleNamespace(base_url='https://example.invalid/v1',model='doubao-test',key='model-secret')
    return CodexTurn(provider,binary=str(binary),runtime_root=str(root))


TOOLS=[{'type':'function','function':{'name':'list_tasks','description':'Read task status',
        'parameters':{'type':'object','properties':{},'additionalProperties':False}}}]


def test_stdio_history_tool_receipt_images_and_final_answer(server,monkeypatch):
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY','must-not-inherit')
    monkeypatch.setenv('EG_ACCESS_TOKEN','must-not-inherit')
    async def check():
        messages=[dict(role='system',content='You are anker.'),dict(role='user',content='My dog is 小白.'),
                  dict(role='assistant',content='I understand.'),dict(role='user',content='tool')]
        turn=turn_for(server)
        async with turn:
            answer=await turn.complete(messages,TOOLS)
            assert answer['tool_calls'][0]['function']['name']=='list_tasks'
            messages.append(answer)
            messages.append(dict(role='tool',tool_call_id='c1',content='{"tasks":[]}'))
            messages.append(dict(role='system',content='No camera does not block conversation.'))
            messages.append(dict(role='user',content=[dict(type='text',text='Historical sample'),
                dict(type='image_url',image_url={'url':'data:image/png;base64,AAAA'})]))
            final=await turn.complete(messages,TOOLS)
            assert final['content']=='任务已查到，尚未启用。'
        assert turn.process.returncode is not None
        assert list(server[2].iterdir())==[]
        wire=[json.loads(s) for s in server[1].read_text().splitlines()]
        first=wire[0]
        assert 'AWS_SECRET_ACCESS_KEY' not in first['env'] and 'EG_ACCESS_TOKEN' not in first['env']
        assert not any('model-secret' in a for a in first['argv'])
        assert 'features.shell_tool=false' in first['argv'] and 'features.goals=false' in first['argv']
        history=next(v['params']['items'] for v in wire if v.get('method')=='thread/inject_items')
        assert [v['role'] for v in history]==['user','assistant']
        start=next(v['params'] for v in wire if v.get('method')=='thread/start')
        assert 'My dog' not in start['baseInstructions']
        assert start['environments']==[] and start['ephemeral'] and not start['allowProviderModelFallback']
        content=next(v['result']['contentItems'] for v in wire if v.get('id')==77 and 'result' in v)
        assert content[-1]['type']=='inputImage' and content[1]['text'].startswith('No camera')
    asyncio.run(check())


@pytest.mark.parametrize('mode',['foreign','unknown','native','fail','malformed','eof'])
def test_fail_closed_and_cleanup(server,mode):
    async def check():
        turn=turn_for(server)
        with pytest.raises(ProviderError) as exc:
            async with turn:
                await turn.complete([dict(role='user',content=mode)],TOOLS)
        assert 'secret-sentinel' not in str(exc.value)
        assert turn.process.returncode is not None and list(server[2].iterdir())==[]
    asyncio.run(check())


def test_cancellation_terminates_process_and_removes_session(server):
    async def check():
        turn=turn_for(server)
        async def run():
            async with turn:
                await turn.complete([dict(role='user',content='stall')],TOOLS)
        task=asyncio.create_task(run())
        while not server[1].exists() or 'turn/start' not in server[1].read_text(): await asyncio.sleep(.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert turn.process.returncode is not None and list(server[2].iterdir())==[]
    asyncio.run(check())


def test_runtime_uses_codex_scoped_tools_and_keeps_post_turn_memory(server,tmp_path,monkeypatch):
    from evidenceguard.harness.runtime import AgentRuntime
    from evidenceguard.harness.tools import ToolRegistry
    from evidenceguard.store import Store
    from unittest.mock import Mock
    monkeypatch.setenv('EG_AGENT_EXECUTOR',EXECUTOR)
    monkeypatch.setenv('EG_CODEX_BINARY',str(server[0]))
    monkeypatch.setenv('EG_CODEX_RUNTIME_DIR',str(server[2]))
    async def check():
        store=Store(tmp_path/'app.sqlite3');registry=ToolRegistry()
        async def tasks():return []
        registry.register('list_tasks',tasks,description='Read tasks')
        provider=SimpleNamespace(name='doubao-test',ready=True,model='doubao-test',base_url='https://example.invalid',key='key')
        agent=AgentRuntime(store,registry,provider)
        memory=Mock();memory.personal.context.return_value={};agent.memory=memory
        run=agent.start('tool','chat',client_id='client-test')
        await asyncio.gather(*agent.tasks.values())
        saved=store.run(run['id'])
        assert saved['executionContract']['executor']==EXECUTOR and saved['status']=='completed'
        assert saved['toolReceipts']==[{'tool':'list_tasks','status':'completed'}]
        memory.enqueue.assert_called_once()
        assert memory.enqueue.call_args.args[0]['status']=='completed'
        assert saved['draft'] is None
        store.close()
    asyncio.run(check())


@pytest.mark.parametrize('raw',['{"valueScore":10}',"{'valueScore':10}",'```json\n{"valueScore":10}\n```'])
def test_structured_format_normalization_does_not_fill_missing_fields(raw):
    from evidenceguard.proactive import Decision
    assert json.loads(structured_text(raw))=={'valueScore':10}
    with pytest.raises(ValueError): Decision.model_validate_json(structured_text(raw))


@pytest.mark.parametrize('raw',["__import__('os').system('echo bad')",'Explanation: {"valueScore":99}',
    '{"valueScore":NaN}',"{'sourceIds':{1,2}}",'[]','x'*16001])
def test_structured_format_rejects_code_prose_and_non_json_values(raw):
    with pytest.raises(ProviderError):structured_text(raw)
