import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from eg_dashboard.briefing import project, processing_status
from eg_dashboard.media_assets import PublicMedia


class PublicBriefingTests(unittest.TestCase):
    def test_requires_exact_current_public_source_and_projects_only_declared_case(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);folder=root/'briefing'/'demo';folder.mkdir(parents=True)
            db=root/'app.db'
            with sqlite3.connect(db) as connection:
                connection.executescript('CREATE TABLE endpoint_analyses(payload TEXT);CREATE TABLE visual_controls(payload TEXT);CREATE TABLE video_search_jobs(payload TEXT);')
                connection.execute('INSERT INTO video_search_jobs VALUES (?)',(json.dumps({'text':'PRIVATE QUERY','secret':'NEVER EXPORT'}),))
                connection.execute('INSERT INTO endpoint_analyses VALUES (?)',(json.dumps({'status':'completed','analysis':'PRIVATE ANALYSIS','auxiliary':{'flow':{'status':'skipped','code':'TIME_UNKNOWN','secret':'PRIVATE FLOW'}}}),))
            connection.close()
            raw=b'\x89PNG\r\n\x1a\npublic-test';sha=hashlib.sha256(raw).hexdigest()
            (folder/(sha+'.png')).write_bytes(raw)
            media={'assetId':sha,'mime':'image/png','label':'real processing output'}
            value={'schema':'evidenceguard.briefing/v1','id':'case','createdAt':100,'servicePid':3,
                'source':{'recordingId':'video-public','assetId':'a'*64},'localVision':{'depthReady':True,'secret':'CONFIG SECRET'},
                'processing':{'media':[media,{'assetId':'../../etc/passwd','mime':'image/png'}],'flow':{'status':'completed','secret':'FLOW SECRET'}},
                'searches':[{'id':'own-search','text':'public water bottle query','api_key':'SECRET KEY','indexSignature':'sig','videos':[{'recordingId':'video-private','summary':'PRIVATE RESULT'},{'recordingId':'video-public','summary':'public result','thumbnailUrl':'https://secret.example/'}]}]}
            (folder/'manifest.json').write_text(json.dumps(value))
            assets=PublicMedia(root,'demo',root/'private')
            record={'name':'media_recordings','data':{'id':'video-public','embeddingSignature':'sig','media':[{'assetId':'a'*64}]}}
            self.assertEqual(project(root,'demo',assets,[],{'pid':3},{'database':str(db)},200),[])
            rows=project(root,'demo',assets,[record],{'pid':3},{'database':str(db)},200)
            encoded=json.dumps(rows)
            for forbidden in ['PRIVATE','SECRET','secret.example','/etc/passwd']:self.assertNotIn(forbidden,encoded)
            self.assertEqual(len(rows),2)
            self.assertEqual(len(rows[0]['data']['media']),1)
            self.assertEqual(rows[1]['data']['videos'][0]['summary'],'public result')
            self.assertTrue(rows[1]['data']['signatureCompatible'])
            skill={'schema':'evidenceguard.skill-case/v1','id':'test-skill','mode':'real_api_draft_only','createdAt':190,
                   'source':value['source'],'referenceMedia':[media], 'model':'actual-test-model',
                   'revisions':[{'id':'draft','status':'draft','canActivate':False,'revision':1,'input':'public request',
                        'clientId':'PRIVATE OWNER','plan':{'target':'bottle','trigger':'leaves','api_key':'SECRET KEY'}},
                        {'id':'active','status':'active','canActivate':True,'input':'PRIVATE ACTIVE'}]}
            (folder/'skills.json').write_text(json.dumps(skill))
            with_skill=project(root,'demo',assets,[record],{'pid':3},{'database':str(db)},200)
            published=next(r['data'] for r in with_skill if r['name']=='media_skill_generation_case')
            self.assertEqual(len(published['revisions']),1)
            self.assertEqual(published['revisions'][0]['plan'],{'target':'bottle','trigger':'leaves'})
            self.assertEqual(len(published['referenceMedia']),1)
            self.assertNotIn('PRIVATE',json.dumps(with_skill));self.assertNotIn('SECRET',json.dumps(with_skill))
            skill['source']={'recordingId':'video-private','assetId':'a'*64}
            (folder/'skills.json').write_text(json.dumps(skill))
            self.assertEqual(len(project(root,'demo',assets,[record],{}, {'database':str(db)},200)),2)
            for malformed in ('{"unfinished"','[]'):
                (folder/'skills.json').write_text(malformed)
                self.assertEqual(len(project(root,'demo',assets,[record],{}, {'database':str(db)},200)),2)
            status=processing_status({'pid':3,'startedAt':190,'guardTracking':'per_run_v1',
                'localVision':{'depthReady':True}}, {'database':str(db)},200)
            self.assertEqual(status['data']['endpoint_analysesCount'],1)
            self.assertTrue(status['data']['sameProcess'])
            self.assertEqual(status['data']['guardRunCoverage'],'per_run_v1')
            self.assertNotIn('PRIVATE',json.dumps(status))
            record['data']['media'][0]['assetId']='changed'
            self.assertEqual(project(root,'demo',assets,[record],{'pid':3},{'database':str(db)},200),[])

    def test_missing_manifest_and_unknown_schema_are_not_success(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)
            self.assertEqual(project(root,'demo',None,[],{}, {},200),[])
            path=root/'briefing'/'demo';path.mkdir(parents=True)
            (path/'manifest.json').write_text('{"schema":"unsupported"}')
            self.assertEqual(project(root,'demo',None,[],{}, {},200),[])


if __name__=='__main__':unittest.main()
