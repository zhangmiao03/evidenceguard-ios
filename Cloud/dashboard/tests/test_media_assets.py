import asyncio
import base64
import contextvars
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from eg_dashboard.media_assets import capture_inputs, PublicMedia
from eg_dashboard.media import read_media
from eg_dashboard.server import create_app
from eg_dashboard.retrieval import observe_search

class MediaAssetTests(unittest.TestCase):
    def test_exact_input_copy_no_remote_fetch_or_secrets_and_read_only_ranges(self):
        from fastapi.testclient import TestClient
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);web=root/'web';(web/'assets').mkdir(parents=True);(web/'index.html').write_text('ok')
            raw=b'\xff\xd8\xff'+b'x'*100
            request={'messages':[{'content':[{'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+base64.b64encode(raw).decode()}},{'image_url':{'url':'https://private.invalid/image?token=hidden'}}]}]}
            rec=SimpleNamespace(path=root/'ops.db')
            self.assertEqual(capture_inputs(request,rec),[])
            with patch.dict(os.environ,{'EG_DASHBOARD_CAPTURE_MEDIA':'1'}):items=capture_inputs(request,rec)
            self.assertEqual(items[0]['assetId'],hashlib.sha256(raw).hexdigest())
            self.assertNotIn('hidden',json.dumps(items));self.assertNotIn('private.invalid',json.dumps(items))
            cache=PublicMedia(root/'public','demo',root/'observer-media');published=cache.reference(items[0]);cache.finish()
            self.assertEqual(published['status'],'available')
            client=TestClient(create_app(root/'public',web));url=published['previewUrl']
            response=client.get(url);self.assertEqual(response.status_code,200);self.assertEqual(response.content,raw)
            self.assertEqual(response.headers['content-type'],'image/jpeg')
            self.assertEqual(client.head(url).status_code,200)
            ranged=client.get(url,headers={'Range':'bytes=0-2'})
            self.assertEqual(ranged.status_code,206);self.assertEqual(ranged.content,raw[:3])
            self.assertEqual(client.post(url).status_code,405)
            self.assertEqual(client.get('/dashboard/api/media/demo/'+'0'*64).status_code,404)
            self.assertEqual(client.get('/dashboard/api/media/unknown/'+items[0]['assetId']).status_code,404)
            self.assertEqual(client.get('/dashboard/api/media/demo/%2e%2e%2fcloud.env').status_code,404)
            PublicMedia(root/'public','demo',root/'observer-media').finish()
            self.assertEqual(client.get(url).status_code,404,'Old copies must not bypass the current manifest')

    def test_unsupported_media_and_large_inputs_do_not_get_published(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'EG_DASHBOARD_CAPTURE_MEDIA':'1'}):
            rec=SimpleNamespace(path=Path(tmp)/'ops.db')
            request={'input':[{'image_url':{'url':'data:image/jpeg;base64,'+base64.b64encode(b'not an image').decode()}}]}
            items=capture_inputs(request,rec)
            self.assertNotIn('assetId',items[0])
            with patch('eg_dashboard.media_assets.MAX_IMAGE',2):
                self.assertNotIn('assetId',capture_inputs({'image_url':{'url':'data:image/jpeg;base64,/9j/eA=='}},rec)[0])

    def test_source_images_join_only_by_stored_references_and_recording_is_scoped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'app.db';raw=b'\xff\xd8\xffabc'
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE media(id TEXT,payload TEXT,bytes BLOB,mime TEXT)')
                db.execute('INSERT INTO media VALUES (?,?,?,?)',('img','{}',raw,'image/jpeg'))
                db.execute('CREATE TABLE sdk_events(id TEXT,payload TEXT)')
                db.execute('INSERT INTO sdk_events VALUES (?,?)',('event',json.dumps({'episodeId':'episode','imageUrl':'/api/media/img','cameraId':'camera'})))
                db.execute('CREATE TABLE sdk_episodes(id TEXT,status TEXT,payload TEXT)')
                db.execute('INSERT INTO sdk_episodes VALUES (?,?,?)',('episode','completed','{}'))
                db.execute('CREATE TABLE recordings(id TEXT,payload TEXT)')
                db.execute('INSERT INTO recordings VALUES (?,?)',('../../secret','{}'))
            db.close()
            cache=PublicMedia(root/'public','demo',root/'observer-media')
            rows,_=read_media(path,123,assets=cache,video_root=root/'recordings')
            ep=next(r['data'] for r in rows if r['name']=='media_sdk_episodes')
            self.assertEqual(ep['media'][0]['provenance'],'stored_source')
            self.assertEqual(ep['media'][0]['assetId'],hashlib.sha256(raw).hexdigest())
            self.assertNotIn(str(root),json.dumps(rows))
            self.assertNotIn('media',next(r['data'] for r in rows if r['name']=='media_recordings'))

class RetrievalTests(unittest.IsolatedAsyncioTestCase):
    async def test_result_exception_and_cancellation_preserved_with_real_arguments(self):
        rows=[]
        ops=SimpleNamespace(CTX=contextvars.ContextVar('ctx',default={}),RECORDER=contextvars.ContextVar('rec',default=None))
        rec=SimpleNamespace(emit=lambda name,**kw:rows.append(dict(name=name,**kw)))
        result={'status':'completed','videos':[{'similarity':.75,'verdict':'uncertain'}]}
        calls=[]
        async def search(query,camera_id=None,progress=None):calls.append(query);return result
        service=SimpleNamespace(search=search);observe_search(service,ops,rec)
        with patch.dict(os.environ,{'EG_DASHBOARD_CAPTURE_CONTENT':'1'}):
            actual=await service.search('where is the box',camera_id='cam')
        self.assertIs(actual,result);self.assertEqual(calls,['where is the box'])
        self.assertEqual(rows[0]['data']['content']['arguments'],{'query':'where is the box','camera_id':'cam'})
        self.assertEqual(rows[0]['data']['content']['result'],result)
        self.assertEqual(ops.CTX.get(),{});self.assertIsNone(ops.RECORDER.get())
        for error in [ValueError('failed'),asyncio.CancelledError()]:
            async def failed(query):raise error
            service=SimpleNamespace(search=failed);observe_search(service,ops,rec)
            with self.assertRaises(type(error)):await service.search('query')
        async def search(query):return result
        service=SimpleNamespace(search=search)
        def broken(*a,**k):raise OSError('observer unavailable')
        observe_search(service,ops,SimpleNamespace(emit=broken))
        self.assertIs(await service.search('query'),result)
