import json
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from eg_dashboard.media import read_media
from eg_dashboard.media_assets import PublicMedia

class IndexedFrames(unittest.TestCase):
    def test_corpus_frame_is_exact_and_private_or_outside_paths_are_not_copied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);video=root/'videos';output=root/'public';path=root/'data.db'
            rid='video-'+('a'*16);sig='b'*64
            frame=video/rid/('index-'+sig[:16])/'frame-00001.jpg'
            frame.parent.mkdir(parents=True);raw=b'\xff\xd8\xffreal-corpus-frame';frame.write_bytes(raw)
            with sqlite3.connect(path) as db:
                db.executescript('''CREATE TABLE retrieval_recordings(id TEXT,active_signature TEXT);
                CREATE TABLE retrieval_clips(id TEXT,recording_id TEXT,signature TEXT,start REAL,end REAL);
                CREATE TABLE retrieval_units(id TEXT,signature TEXT,dimensions INTEGER,vector BLOB);
                CREATE TABLE retrieval_embeddings(unit_id TEXT,clip_id TEXT,signature TEXT,kind TEXT,offset_ms INTEGER,thumbnail TEXT);''')
                db.execute('INSERT INTO retrieval_recordings VALUES (?,?)',(rid,sig))
                db.execute('INSERT INTO retrieval_clips VALUES (?,?,?,?,?)',('clip',rid,sig,0,20))
                db.execute('INSERT INTO retrieval_units VALUES (?,?,?,?)',('u',sig,1024,struct.pack('<1024f',1,*([0]*1023))))
                for offset,thumbnail in enumerate([str(frame.relative_to(video)).replace('\\','/'),'../private.jpg','video-query-images/private.jpg',str(frame),str(frame.relative_to(video)).replace('frame-00001','frame-99999')]):
                    db.execute('INSERT INTO retrieval_embeddings VALUES (?,?,?,?,?,?)',('u','clip',sig,'frame',offset,thumbnail))
            db.close()
            assets=PublicMedia(output,'demo',root/'inputs')
            rows,_=read_media(path,1,sig,assets,video)
            copied=[r for r in rows if r['data'].get('media')]
            self.assertEqual(len(copied),1)
            media=copied[0]['data']['media'][0]
            self.assertEqual(media['provenance'],'indexed_frame')
            self.assertEqual((assets.root/(media['assetId']+'.jpg')).read_bytes(),raw)
            self.assertNotIn('private.jpg',json.dumps(rows))
            self.assertNotIn(str(video),json.dumps(rows))

if __name__=='__main__':unittest.main()
