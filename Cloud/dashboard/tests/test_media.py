import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from eg_dashboard.media import read_media


class MediaProjectionTests(unittest.TestCase):
    def test_snapshot_has_actual_dimensions_signature_and_no_source_media(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'media.db'
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE recordings (id TEXT PRIMARY KEY,payload TEXT)')
                db.execute('INSERT INTO recordings VALUES (?,?)',('video-1',json.dumps(dict(id='video-1',status='ready',cameraId='cam-a',sourceType='synthetic_review',embeddingSignature='sig',sourceReference='secret-video-url',title='testing'))))
                db.execute('CREATE TABLE video_segments (id TEXT,recording_id TEXT,signature TEXT,payload TEXT,vector TEXT)')
                db.execute('INSERT INTO video_segments VALUES (?,?,?,?,?)',('seg-1','video-1','sig',json.dumps(dict(start=0,end=10,path='/private/video.mp4',cameraId='cam-a')),json.dumps([0.6,0.8])))
                db.execute('INSERT INTO video_segments VALUES (?,?,?,?,?)',('seg-2','video-1','old','{}','[0,0]'))
                db.execute('CREATE TABLE sdk_episodes (id TEXT,status TEXT,payload TEXT)')
                episode=dict(status='pending',review=dict(status='completed',review=dict(visible='box',uncertainties='occluded',imageUrl='private-image'),api_key='secret-value'))
                db.execute('INSERT INTO sdk_episodes VALUES (?,?,?)',('ep','completed',json.dumps(episode)))
            db.close()
            rows,summary=read_media(path,100,'sig')
            encoded=json.dumps(rows)
            for secret in ('secret-video-url','/private/video.mp4','private-image','secret-value'):self.assertNotIn(secret,encoded)
            segment=next(r['data'] for r in rows if r['name']=='media_video_segments' and r['data']['id']=='seg-1')
            self.assertEqual(segment['dimensions'],2);self.assertEqual(segment['norm'],1)
            self.assertTrue(segment['signatureCompatible']);self.assertTrue(segment['normalized'])
            self.assertEqual(summary['invalidVectorsInSample'],1)
            self.assertEqual(summary['tables']['video_segments']['matchingSignature'],1)
            self.assertEqual(next(r['data']['status'] for r in rows if r['name']=='media_sdk_episodes'),'completed')
            self.assertEqual(next(r['data']['sourceType'] for r in rows if r['name']=='media_recordings'),'synthetic_review')
            unknown,_=read_media(path,101)
            self.assertIsNone(next(r['data']['signatureCompatible'] for r in unknown if r['name']=='media_recordings'))

    def test_missing_tables_are_unknown_and_collection_is_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'empty.db'
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE video_segments (id TEXT,recording_id TEXT,signature TEXT,payload TEXT,vector TEXT)')
                db.executemany('INSERT INTO video_segments VALUES (?,?,?,?,?)',[(str(n),'v','s','{}','[1]') for n in range(125)])
            db.close()
            rows,summary=read_media(path,1)
            self.assertEqual(len(rows),120)
            self.assertTrue(summary['tables']['video_segments']['truncated'])
            self.assertEqual(summary['tables']['video_segments']['total'],125)
            self.assertIsNone(summary['tables']['recordings']['total'])
            self.assertIsNone(summary['tables']['video_segments']['matchingSignature'])

if __name__=='__main__':unittest.main()
