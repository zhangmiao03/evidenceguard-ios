from __future__ import annotations
import json


class VideoStore:
    def __init__(self,store):
        self.store=store
        with store.transaction():
            store.db.execute('CREATE TABLE IF NOT EXISTS recordings (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            store.db.execute('CREATE TABLE IF NOT EXISTS video_segments (id TEXT PRIMARY KEY, recording_id TEXT NOT NULL, signature TEXT NOT NULL, payload TEXT NOT NULL, vector TEXT NOT NULL)')
            store.db.execute('CREATE INDEX IF NOT EXISTS video_segment_signature ON video_segments(signature,recording_id)')

    def save_recording(self,item):
        with self.store.transaction():
            self.store.db.execute('INSERT INTO recordings VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',(item['id'],json.dumps(item,ensure_ascii=False)))
        return item

    def recording(self,rid):
        with self.store.lock: row=self.store.db.execute('SELECT payload FROM recordings WHERE id=?',(rid,)).fetchone()
        if not row: raise KeyError(rid)
        return json.loads(row[0])

    def recordings(self,camera_id=None):
        with self.store.lock: rows=self.store.db.execute('SELECT payload FROM recordings ORDER BY json_extract(payload,\'$.createdAt\') DESC').fetchall()
        return [r for row in rows if (r:=json.loads(row[0])) and (not camera_id or r['cameraId']==camera_id)]

    def segments(self,signature=None):
        query='SELECT payload,vector FROM video_segments'; params=()
        if signature: query+=' WHERE signature=?'; params=(signature,)
        with self.store.lock: rows=self.store.db.execute(query,params).fetchall()
        return [(json.loads(r[0]),json.loads(r[1])) for r in rows]

    def publish(self,recording,segments):
        # No partially indexed recording is searchable. Failed imports remain retryable.
        with self.store.transaction():
            self.store.db.execute('DELETE FROM video_segments WHERE recording_id=?',(recording['id'],))
            for item,vector in segments:
                self.store.db.execute('INSERT INTO video_segments VALUES (?,?,?,?,?)',
                    (item['id'],recording['id'],item['signature'],json.dumps(item,ensure_ascii=False),json.dumps(vector)))
            recording.update(status='ready',error=None,segmentCount=len(segments))
            self.save_recording(recording)
