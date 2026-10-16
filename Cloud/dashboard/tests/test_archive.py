import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from eg_dashboard.archive import project, read_page, display_check
from eg_dashboard.media_assets import PublicMedia
from eg_dashboard.server import create_app


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.business=self.root/'business.db';self.obs=self.root/'ops.db'
        self.now=time.time()
        with sqlite3.connect(self.business) as db:
            db.executescript('CREATE TABLE media(id TEXT,payload TEXT,bytes BLOB,mime TEXT); CREATE TABLE runs(id TEXT,payload TEXT); CREATE TABLE video_query_images(id TEXT,payload TEXT);')
            for i in range(171):
                image=Image.new('RGB',(2,2),(i,0,0));buf=io.BytesIO();image.save(buf,format='PNG')
                frame={'device_id':'camera-1','received_at':1000+i//2,'source_type':'official_live_ios'}
                db.execute('INSERT INTO media VALUES (?,?,?,?)',(f'image-{i:03}',json.dumps({'frame':frame}),buf.getvalue(),'image/png'))
            for i in range(97):
                run={'id':f'run-{i:03}','text':'真实回复 private-secret-abcdefgh','createdAt':1000+i//2,'status':'completed','clientPlatform':'ios'}
                if i==0: run['referenceImageId']='private-reference'
                db.execute('INSERT INTO runs VALUES (?,?)',(run['id'],json.dumps(run)))
            db.execute('INSERT INTO video_query_images VALUES (?,?)',('private-reference','private-query-image-canary'))
        db.close()
        with sqlite3.connect(self.obs) as db:
            db.execute('CREATE TABLE records(id TEXT,at REAL,payload TEXT)')
            row=dict(id='receipt',kind='event',name='agent.displayed',at=2000,traceId='run-096',spanId='s',source='client',platform='ios',status='completed',data={'backendTextHash':hashlib.sha256('真实回复 private-secret-abcdefgh'.encode()).hexdigest(),'displayTextHash':'b'*64,'presentationVersion':'v1','appVersion':'1/17'})
            db.execute('INSERT INTO records VALUES (?,?,?)',('receipt',2000,json.dumps(row)))
        db.close()
        self.assets=PublicMedia(self.root,'demo',self.root/'input')
        self.summary=project(self.business,self.obs,self.root,'demo',self.now,self.assets,secrets=['private-secret-abcdefgh'],capture=True)
        self.assets.finish();(self.root/'assets').mkdir();(self.root/'index.html').write_text('Dashboard')
        self.client=TestClient(create_app(self.root,self.root))

    def tearDown(self): self.tmp.cleanup()

    def test_full_inventory_past_old_caps_and_stable_cursor_ties(self):
        ids=[];cursor=''
        while True:
            page=read_page(self.root/'demo-archive.sqlite3','images',cursor=cursor,limit=12)
            ids.extend(i['id'] for i in page['items'])
            if not page['nextCursor']:break
            cursor=page['nextCursor']
        self.assertEqual(len(ids),171);self.assertEqual(len(set(ids)),171)
        self.assertEqual(self.summary['images']['previewable'],171)
        for descriptor in self.assets.manifest.values():
            self.assertEqual(self.client.get('/dashboard/api/media/demo/'+descriptor['assetId']).status_code,200)

    def test_history_backfill_is_sanitized_and_does_not_forge_steps(self):
        reply=self.client.get('/dashboard/api/archive/replies?limit=1').json()['items'][0]
        self.assertIn('[redacted]',reply['answer']);self.assertNotIn('private-secret',reply['answer'])
        self.assertEqual(reply['displayVerification']['status'],'backend_match')
        self.assertEqual(reply['retainedSteps'],1)
        exported=self.client.get('/dashboard/api/archive/replies/export').text
        values=[json.loads(line) for line in exported.splitlines()]
        self.assertEqual(len(values),97)
        self.assertNotIn('private-query-image-canary',exported)
        self.assertNotIn('private-secret-abcdefgh',exported)
        private=next(v for v in values if v['id']=='run-000')
        self.assertIsNone(private['answer']);self.assertEqual(private['bodyStatus'],'private_content')
        historic=next(v for v in values if v['id']=='run-002')
        self.assertEqual(historic['historyStatus'],'steps_not_retained_or_not_captured')
        step=self.client.get('/dashboard/api/archive-trace/run-096').json()
        self.assertEqual(len(step['records']),1)

    def test_anonymous_scoped_export_read_only_and_invalid_params(self):
        url='/dashboard/api/archive/images'
        self.assertEqual(self.client.get(url+'?platform=ios').json()['total'],171)
        self.assertEqual(self.client.get(url+'?platform=web').json()['total'],0)
        self.assertEqual(self.client.get(url+'?device=wrong').json()['total'],0)
        self.assertEqual(self.client.get(url+'?query=source_type').json()['total'],0)
        self.assertEqual(self.client.get(url+'?cursor=malformed').status_code,422)
        self.assertEqual(self.client.get(url+'?limit=500').status_code,422)
        self.assertEqual(self.client.get(url+'?environment=../../etc').status_code,422)
        self.assertEqual(self.client.post(url).status_code,405)
        self.assertEqual(self.client.get(url+'/export?platform=web').text,'')
        self.assertEqual(len(self.client.get(url+'/export?platform=ios').text.splitlines()),171)

    def test_secret_source_missing_fails_closed_and_mismatch_never_passes(self):
        project(self.business,self.obs,self.root,'team',self.now,self.assets,secrets=None,capture=True)
        result=read_page(self.root/'team-archive.sqlite3','replies',limit=1)['items'][0]
        self.assertIsNone(result['answer']);self.assertEqual(result['bodyStatus'],'capture_disabled')
        receipt={'traceId':'r','at':1,'data':{'backendTextHash':'0'*64}}
        self.assertEqual(display_check({'id':'r','text':'answer'},[receipt])['status'],'backend_mismatch')
        self.assertEqual(display_check({'id':'r','text':'answer'},[])['status'],'not_reported')

if __name__=='__main__':unittest.main()
