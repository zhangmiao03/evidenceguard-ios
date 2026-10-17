import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from eg_dashboard.collector import Collector, compare_files, public_record, public_value, read_business, readonly
from eg_dashboard.server import create_app
from fastapi.testclient import TestClient


class PublicDashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        (self.root/'assets').mkdir();(self.root/'index.html').write_text('<h1>Dashboard</h1>')
        self.bundle={'schemaVersion':'evidenceguard.ops/v1','dataset':{'id':'cloud-demo','title':'Demo','source':'local','exportedAt':time.time()},'records':[],'coverage':{}}
        (self.root/'demo.json').write_text(json.dumps(self.bundle))
        self.client=TestClient(create_app(self.root,self.root))

    def tearDown(self):self.temp.cleanup()

    def test_anonymous_read_only_routes(self):
        self.assertEqual(self.client.get('/dashboard').status_code,200)
        self.assertEqual(self.client.get('/dashboard/index.html').status_code,200)
        self.assertEqual(self.client.get('/dashboard/downloads/evidenceguard-website.zip').status_code,404)
        (self.root/'downloads').mkdir()
        (self.root/'downloads/evidenceguard-website.zip').write_bytes(b'PK-test-archive')
        self.assertEqual(self.client.get('/dashboard/downloads/evidenceguard-website.zip').headers['content-type'],'application/zip')
        self.assertEqual(self.client.head('/dashboard').status_code,200)
        self.assertTrue(self.client.get('/dashboard/api/info').json()['readOnly'])
        self.assertEqual(self.client.get('/dashboard/api/snapshot').status_code,200)
        self.assertEqual(self.client.get('/api/agent/runs').status_code,404)
        for method in ('post','put','patch','delete'):
            self.assertEqual(getattr(self.client,method)('/dashboard/api/snapshot').status_code,405)
        self.assertEqual(self.client.get('/dashboard/api/snapshot',params={'environment':'../../etc/passwd'}).status_code,422)
        self.assertEqual(self.client.get('/dashboard/api/snapshot?environment=team').status_code,503)
        self.assertEqual(self.client.get('/dashboard').headers['cache-control'],'no-store')

    def test_stale_and_corrupt_snapshots_never_appear_fresh(self):
        self.bundle['dataset']['exportedAt']-=40
        (self.root/'demo.json').write_text(json.dumps(self.bundle))
        self.assertTrue(self.client.get('/dashboard/api/snapshot').json()['coverage']['stale'])
        (self.root/'demo.json').write_text('not json')
        self.assertEqual(self.client.get('/dashboard/api/snapshot').status_code,503)

    def test_public_prompts_reapply_redaction_even_when_capture_was_enabled(self):
        row={'id':'p','kind':'prompt','data':{'contentCapture':True,'request':{'messages':[
            {'role':'system','content':'fixed instructions'}, {'role':'system','content':'private memory'},
            {'role':'user','content':'user secret phrase'}, {'role':'assistant','content':'private response','tool_calls':[{'private':'payload'}]}],
            'input':'private image data','api_key':'do-not-export'}}}
        result=public_record(row)
        encoded=json.dumps(result)
        self.assertIn('fixed instructions',encoded)
        for secret in ('private memory','user secret phrase','private response','payload','private image data','do-not-export'):
            self.assertNotIn(secret,encoded)
        self.assertFalse(result['data']['contentCapture'])
        self.assertTrue(result['data']['publicProjection'])
        self.assertEqual(public_value(float('nan')),None)
        fake_access_key = 'AKIA' + '0' * 16
        self.assertNotIn(fake_access_key,public_value(fake_access_key))

    def test_business_snapshot_is_read_only_and_not_a_transcript(self):
        p=self.root/'business.sqlite3'
        with sqlite3.connect(p) as db:
            db.execute('CREATE TABLE runs (id TEXT, payload TEXT)')
            db.execute('INSERT INTO runs VALUES (?,?)',('r',json.dumps({'id':'r','status':'completed','message':'private message','text':'private answer','imageBase64':'private image'})))
        db.close()
        rows,counts=read_business(p,time.time())
        self.assertEqual(counts['runs'],1)
        self.assertEqual(rows[0]['data'],{'id':'r','status':'completed'})
        with readonly(p) as db:
            with self.assertRaises(sqlite3.OperationalError):db.execute('DELETE FROM runs')

    def test_deployment_comparison_and_missing_observer_are_honest(self):
        self.assertEqual([v['status'] for v in compare_files({'a':'1','b':'2'},{'a':'0','c':'3'})],['changed','extra','missing'])
        source=self.root/'source';source.mkdir();(source/'app.py').write_text('value=1')
        reference=self.root/'reference.json';reference.write_text(json.dumps({'revision':'a'*40,'files':{'app.py':'different'}}))
        env={'title':'Demo','source':str(source),'state':str(self.root/'missing-state'),'observations':str(self.root/'missing-ops'),'database':str(self.root/'missing-db'),'service':'service'}
        collector=Collector({'output':str(self.root/'out'),'reference':str(reference),'environments':{'demo':env}})
        bundle=collector.bundle('demo',env,{'services':[{'environment':'demo','pid':12}]})
        self.assertEqual(bundle['coverage']['observability'],'unavailable')
        self.assertIsNone(bundle['coverage']['totalStored'])
        self.assertFalse(bundle['coverage']['deployment']['processMatchesObserver'])
        self.assertEqual(bundle['coverage']['deployment']['diskVsRepository'][0]['status'],'changed')
        self.assertFalse((self.root/'missing-ops').exists())
        self.assertFalse((self.root/'missing-db').exists())


if __name__=='__main__':unittest.main()
