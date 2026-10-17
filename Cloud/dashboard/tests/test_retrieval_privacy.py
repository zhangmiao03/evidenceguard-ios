import contextvars
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from eg_dashboard.retrieval import observe_search

class RetrievalPrivacyTests(unittest.IsolatedAsyncioTestCase):
    async def test_v2_search_does_not_publish_query_or_result_after_private_context_exits(self):
        recorded=[]
        class Recorder:
            def emit(self,name,**kw):recorded.append(kw)
        async def search(query,*,image_ref=None,owner=None):
            return {'candidateCount':2,'videos':[{'summary':'private result'}]}
        service=SimpleNamespace(v2_enabled=True,search=search)
        ops=SimpleNamespace(CTX=contextvars.ContextVar('ctx',default={}),RECORDER=contextvars.ContextVar('rec',default=None),PRIVATE_CONTENT=contextvars.ContextVar('private',default=False))
        observe_search(service,ops,Recorder())
        with patch('eg_dashboard.content.details',side_effect=AssertionError('must not capture private body')):
            result=await service.search('private query',image_ref='private-image-ref',owner='private-owner')
        self.assertEqual(result['candidateCount'],2)
        self.assertEqual(recorded[0]['data'],{'privateContent':True,'candidateCount':2})
        self.assertNotIn('private query',json.dumps(recorded))

    async def test_legacy_text_search_keeps_authorized_result_body(self):
        recorded=[]
        class Recorder:
            def emit(self,name,**kw):recorded.append(kw)
        async def search(query):return {'candidateCount':1}
        service=SimpleNamespace(search=search)
        ops=SimpleNamespace(CTX=contextvars.ContextVar('ctx2',default={}),RECORDER=contextvars.ContextVar('rec2',default=None))
        observe_search(service,ops,Recorder())
        with patch('eg_dashboard.content.details',return_value={'content':{'result':{'candidateCount':1}}}):
            result=await service.search('box')
        self.assertEqual(recorded[0]['data']['query'],'box')
        self.assertEqual(recorded[0]['data']['content']['result'],result)
