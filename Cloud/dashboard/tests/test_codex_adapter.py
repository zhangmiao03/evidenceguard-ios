import asyncio
import base64
import contextvars
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eg_dashboard import codex_adapter, content


class CodexTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'EG_DASHBOARD_CAPTURE_CONTENT':'1', 'EG_CODEX_MODEL_KEY':'private-test-credential'})
        self.env.start(); self.addCleanup(self.env.stop)
        class Turn:
            def __init__(self):
                self.provider = SimpleNamespace(model='actual-configured-model')
                self.thread_id = None; self.turn_id = None
                self.sent = []; self.incoming = []; self.calls = 0
                self.result = {'role':'assistant', 'content':'Final answer'}
            async def send(self, value): self.sent.append(value)
            async def read(self): return self.incoming.pop(0)
            async def complete(self, messages, tools):
                self.calls += 1
                self.inputs = (messages, tools)
                await self.send({'id':1, 'method':'thread/start', 'params':{
                    'baseInstructions':messages[0]['content'] + '\nAdapter-added instruction', 'dynamicTools':tools}})
                self.thread_id = 'thread-real'; self.turn_id = 'turn-real'
                while self.incoming: await self.read()
                return self.result
        self.cls = Turn
        self.rows = []
        def emit(name, **kwargs):
            self.rows.append(dict(name=name, **kwargs, context=dict(self.ops.CTX.get())))
        self.ops = SimpleNamespace(
            CTX=contextvars.ContextVar('codex-test-ctx', default={'traceId':'real-run', 'spanId':'parent'}),
            RECORDER=contextvars.ContextVar('codex-test-rec', default=SimpleNamespace(emit=emit)),
            digest=lambda value:hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest(),
            prompt_snapshot=lambda body, capture: {'request':{'model':body['model']}, 'contentCapture':False})
        codex_adapter.install(self.ops, Turn)
        self.turn = Turn()

    async def test_actual_protocol_inputs_outputs_preserved_and_private_items_excluded(self):
        messages = [{'role':'system','content':'Host prompt private-test-credential'}]
        tools = [{'function':{'name':'list_tasks','parameters':{'type':'object'}}}]
        private = {'method':'item/completed','params':{'item':{'type':'reasoning','text':'hidden-thought'}}}
        self.turn.incoming = [private,
            {'method':'item/tool/call','params':{'tool':'list_tasks','arguments':{'password':'never-show'}}},
            {'method':'item/completed','params':{'item':{'type':'agentMessage','text':'Final answer'}}},
            {'method':'turn/completed','params':{'turn':{'id':'turn-real','status':'completed','items':[private]}}}]
        result = await self.turn.complete(messages, tools)
        self.assertIs(result, self.turn.result)
        self.assertIs(self.turn.inputs[0], messages)
        self.assertEqual(self.turn.calls, 1)
        self.assertIn('private-test-credential', self.turn.sent[0]['params']['baseInstructions'])
        encoded = json.dumps(self.rows)
        for forbidden in ('private-test-credential','never-show','hidden-thought'):
            self.assertNotIn(forbidden, encoded)
        self.assertIn('Adapter-added instruction', encoded)
        models = [r for r in self.rows if r.get('kind')=='model']
        prompts = [r for r in self.rows if r.get('kind')=='prompt']
        self.assertEqual(len(models),1); self.assertEqual(len(prompts),1)
        self.assertEqual(models[0]['data']['promptId'], prompts[0]['record_id'])
        self.assertFalse(models[0]['data']['wireHttpVisible'])
        self.assertIsNone(models[0]['data']['usage'])
        self.assertEqual(models[0]['status'],'executor_ok')
        self.assertEqual(self.ops.CTX.get()['spanId'], 'parent')

    async def test_usage_snapshots_are_not_reported_as_per_step_usage(self):
        usage={'method':'thread/tokenUsage/updated','params':{'tokenUsage':{'last':{'totalTokens':90},'total':{'totalTokens':180}}}}
        self.turn.incoming=[usage,usage]
        await self.turn.complete([{'role':'system','content':'test'}], [])
        self.assertEqual(sum(r['name']=='codex.usage' for r in self.rows),2)
        self.assertIsNone(next(r['data']['usage'] for r in self.rows if r.get('kind')=='model'))

    async def test_image_input_keeps_executor_boundary_without_claiming_wire_http(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'EG_DASHBOARD_CAPTURE_MEDIA':'1'}):
            self.ops.RECORDER.get().path=str(Path(folder)/'ops.db')
            raw=b'\xff\xd8\xfftest-image'
            messages=[{'role':'system','content':'system'}, {'role':'user','content':[{'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+base64.b64encode(raw).decode()}}]}]
            result=await self.turn.complete(messages,[])
            self.assertIs(result,self.turn.result)
            prompt=next(r['data'] for r in self.rows if r.get('kind')=='prompt')
            item=prompt['inputMedia'][0]
            self.assertEqual(item['assetId'],hashlib.sha256(raw).hexdigest())
            self.assertEqual(item['provenance'],'executor_input')
            self.assertEqual(prompt['inputBoundary'],'host_to_codex')
            self.assertNotIn('data:image',json.dumps(self.rows))
            self.assertEqual(self.turn.calls,1)

    async def test_errors_cancellation_and_observer_failures_do_not_change_execution(self):
        for error,status in ((RuntimeError('original failure'),'failed'),(asyncio.CancelledError(),'cancelled')):
            class Failure:
                provider=SimpleNamespace(model='model'); thread_id=None; turn_id=None
                calls=0
                async def complete(self, messages, tools): self.calls+=1; raise error
                async def send(self, value): pass
                async def read(self): pass
            codex_adapter.install(self.ops, Failure)
            turn=Failure()
            with self.assertRaises(type(error)) as raised: await turn.complete([], [])
            self.assertIs(raised.exception,error)
            self.assertEqual(turn.calls,1); self.assertEqual(self.rows[-1]['status'],status)
            self.assertEqual(self.ops.CTX.get()['spanId'],'parent')
        with patch.object(content,'clean',side_effect=ValueError('observation only')):
            self.assertIs(await self.turn.complete([{'role':'system','content':'test'}],[]),self.turn.result)
        self.ops.RECORDER.set(SimpleNamespace(emit=lambda *args,**kw: (_ for _ in ()).throw(OSError('full disk'))))
        self.assertIs(await self.turn.complete([{'role':'system','content':'test'}],[]),self.turn.result)

    async def test_disabled_capture_does_not_leak_protocol_text_and_install_is_idempotent(self):
        codex_adapter.install(self.ops,self.cls)
        with patch.dict(os.environ,{'EG_DASHBOARD_CAPTURE_CONTENT':'0'}):
            await self.turn.complete([{'role':'system','content':'private user context'}],[])
        self.assertNotIn('private user context',json.dumps(self.rows))
        self.assertEqual(sum(r.get('kind')=='model' for r in self.rows),1)


if __name__=='__main__': unittest.main()
