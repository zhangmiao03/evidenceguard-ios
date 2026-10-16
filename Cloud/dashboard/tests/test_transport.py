import asyncio
import contextvars
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from eg_dashboard import content, transport


class TransportTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        async def original(client,url,**kwargs): return await client.post(url,**kwargs)
        self.ops=SimpleNamespace(model_post=original, safe=lambda v:v,
            CTX=contextvars.ContextVar('testctx',default={'traceId':'test','spanId':'parent'}),
            RECORDER=contextvars.ContextVar('testrec',default=None), OPERATION=contextvars.ContextVar('testop',default='chat'),
            digest=lambda v:hashlib.sha256(json.dumps(v,sort_keys=True).encode()).hexdigest())
        ops=self.ops
        class Recorder:
            def __init__(self, capacity=2048): self.capacity=capacity;self.rows=[];self.write_errors=0
            def emit(self,name,**kwargs): self.rows.append(dict(name=name,**(kwargs | {'data':ops.safe(kwargs.get('data',{}))})))
        self.ops.Recorder=Recorder
        with patch.dict(os.environ,{'EG_DASHBOARD_CAPTURE_CONTENT':'1'}):transport.install(self.ops)
        self.rec=Recorder();self.ops.RECORDER.set(self.rec)

    async def test_500_response_remains_500_with_one_transport_attempt(self):
        response=SimpleNamespace(status_code=500,headers={'x-request-id':'rid'},json=lambda:{'error':{'message':'bad request','api_key':'key-do-not-show'}})
        count=0
        async def post(*args,**kwargs):
            nonlocal count;count+=1;return response
        with patch.dict(os.environ,{'EG_DASHBOARD_CAPTURE_CONTENT':'1'}):
            result=await self.ops.model_post(SimpleNamespace(post=post),'https://model.invalid/chat',headers={'Authorization':'Bearer do-not-copy'},json={'model':'test','messages':[]})
        self.assertIs(result,response);self.assertEqual(count,1);self.assertEqual(self.rec.capacity,64)
        self.assertEqual(self.rec.rows[-1]['status'],'http_error')
        self.assertNotIn('key-do-not-show',json.dumps(self.rec.rows))
        self.assertNotIn('do-not-copy',json.dumps(self.rec.rows))

    async def test_errors_and_cancellation_are_not_retried_or_swallowed(self):
        for error,status in ((RuntimeError('transport failed'),'failed'),(asyncio.CancelledError(),'cancelled')):
            calls=[]
            async def post(*args,**kwargs): calls.append(1);raise error
            with self.assertRaises(type(error)):
                await self.ops.model_post(SimpleNamespace(post=post),'https://model.invalid/chat',headers={},json={'model':'test'})
            self.assertEqual(len(calls),1);self.assertEqual(self.rec.rows[-1]['status'],status)

    async def test_snapshot_failure_preserves_the_model_result(self):
        response=SimpleNamespace(status_code=200,headers={},json=lambda:{'choices':[]})
        calls=[]
        async def post(*args,**kwargs): calls.append(1);return response
        with patch.dict(os.environ,{'EG_DASHBOARD_CAPTURE_CONTENT':'1'}), patch.object(content,'clean',side_effect=ValueError):
            # Real Recorder.emit is already fail-open; mimic a full queue here.
            self.rec.emit=lambda *args,**kwargs:None
            result=await self.ops.model_post(SimpleNamespace(post=post),'https://model.invalid/chat',headers={},json={'model':'test'})
        self.assertIs(result,response);self.assertEqual(len(calls),1)


if __name__=='__main__':unittest.main()
