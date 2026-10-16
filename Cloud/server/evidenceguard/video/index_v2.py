"""Versioned, resumable video/frame index. The database is one authenticated team.

No caller-supplied tenant ID and no cross-deployment cache. Vectors are read only
after SQL scope filtering, in 1024-row blocks (4 MiB), on a worker thread.
"""
from __future__ import annotations
import hashlib, json, math, time, threading
from collections import OrderedDict
import numpy as np

DIMENSIONS = 1024
BLOCK_ROWS = 1024
CACHE_BYTES = 64 * 1024 * 1024


def vector_blob(value):
    raw = np.asarray(value)
    if raw.shape != (DIMENSIONS,) or raw.dtype.kind not in 'fiu':
        raise ValueError('向量必须是 1024 维数值')
    data = raw.astype(np.float64)
    norm = np.linalg.norm(data)
    if not np.isfinite(data).all() or not math.isfinite(norm) or norm <= 0:
        raise ValueError('向量包含无效数值或零模长')
    return (data / norm).astype('<f4').tobytes()


def top(values, count=20):
    """Partial top-k, with deterministic ordering for equal scores."""
    if not values: return []
    keys = sorted(values)
    scores = np.array([values[k][0] for k in keys], dtype=np.float32)
    if len(keys) > count:
        threshold = np.partition(scores, len(keys)-count)[len(keys)-count]
        chosen = np.flatnonzero(scores >= threshold)
    else: chosen = range(len(keys))
    return sorted(((keys[i], *values[keys[i]]) for i in chosen), key=lambda x: (-x[1], x[0]))[:count]


def fuse(video, frames, clips, limit):
    ranks = {}
    for kind, values in (('video', video), ('frame', frames)):
        for rank, (clip_id, score, frame) in enumerate(top(values), 1):
            entry = ranks.setdefault(clip_id, dict(score=0., ranks={}, frame=None))
            entry['score'] += 1 / (60 + rank)
            entry['ranks'][kind] = dict(rank=rank, cosine=float(score))
            if kind == 'frame': entry['frame'] = frame
    result = []
    for clip_id, ranking in sorted(ranks.items(), key=lambda x: (-x[1]['score'], x[0])):
        clip = clips[clip_id]
        duplicate = next((v for v in result if v['clip']['continuityId'] == clip['continuityId']
                          and v['clip']['cameraId'] == clip['cameraId']
                          and max(0, min(v['clip']['end'], clip['end'])-max(v['clip']['start'], clip['start']))
                          / min(v['clip']['end']-v['clip']['start'], clip['end']-clip['start']) >= .5), None)
        if duplicate:
            duplicate['intervals'].append([clip['start'], clip['end']])
        else:
            result.append(dict(clip=clip, **ranking, intervals=[[clip['start'], clip['end']]]))
    return result[:limit]


class RetrievalIndex:
    def __init__(self, store):
        self.store = store
        self.cache = OrderedDict()
        self.cache_size = 0
        self.cache_generation = None
        self.cache_lock = threading.RLock()
        with store.transaction():
            for sql in (
                '''CREATE TABLE IF NOT EXISTS retrieval_recordings (
                    id TEXT PRIMARY KEY, scope TEXT NOT NULL, camera_id TEXT NOT NULL,
                    source TEXT NOT NULL, recorded_at REAL, duration REAL, active_signature TEXT, payload TEXT NOT NULL)''',
                'CREATE INDEX IF NOT EXISTS retrieval_scope ON retrieval_recordings(scope,active_signature,camera_id,recorded_at,source)',
                '''CREATE TABLE IF NOT EXISTS retrieval_clips (
                    id TEXT NOT NULL, signature TEXT NOT NULL, recording_id TEXT NOT NULL,
                    start REAL NOT NULL, end REAL NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(id,signature))''',
                'CREATE INDEX IF NOT EXISTS retrieval_clip_recording ON retrieval_clips(recording_id,signature,start,end)',
                '''CREATE TABLE IF NOT EXISTS retrieval_units (
                    id TEXT PRIMARY KEY, signature TEXT NOT NULL, model TEXT NOT NULL,
                    dimensions INTEGER NOT NULL CHECK(dimensions=1024), vector BLOB NOT NULL CHECK(length(vector)=4096))''',
                '''CREATE TABLE IF NOT EXISTS retrieval_embeddings (
                    clip_id TEXT NOT NULL, signature TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('video','frame')),
                    offset_ms INTEGER NOT NULL, unit_id TEXT NOT NULL, thumbnail TEXT,
                    PRIMARY KEY(clip_id,signature,kind,offset_ms))''',
                'CREATE INDEX IF NOT EXISTS retrieval_embedding_signature ON retrieval_embeddings(signature,clip_id)',
                '''CREATE TABLE IF NOT EXISTS retrieval_index_jobs (
                    recording_id TEXT NOT NULL, signature TEXT NOT NULL, status TEXT NOT NULL,
                    completed_units INTEGER NOT NULL DEFAULT 0, retry_count INTEGER NOT NULL DEFAULT 0,
                    error TEXT, PRIMARY KEY(recording_id,signature))''',
                'CREATE TABLE IF NOT EXISTS retrieval_meta (key TEXT PRIMARY KEY,value INTEGER NOT NULL)',
            ): store.db.execute(sql)
            store.db.execute("INSERT OR IGNORE INTO retrieval_meta VALUES ('generation',0)")

    @property
    def generation(self):
        with self.store.lock:
            return self.store.db.execute("SELECT value FROM retrieval_meta WHERE key='generation'").fetchone()[0]

    def invalidate(self):
        with self.cache_lock:
            self.cache.clear(); self.cache_size=0; self.cache_generation=None

    def cached_block(self, generation, scope, last, load):
        key=(scope,last)
        with self.cache_lock:
            if self.cache_generation!=generation:
                self.cache.clear(); self.cache_size=0; self.cache_generation=generation
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
        rows=load()
        matrix=np.frombuffer(b''.join(r[5] for r in rows),dtype='<f4').reshape(-1,DIMENSIONS)
        metadata=[r[:5] for r in rows]
        value=(metadata,matrix)
        with self.cache_lock:
            # Publication/deletion during the SQL read invalidates this block.
            if self.cache_generation==generation and matrix.nbytes<=CACHE_BYTES:
                while self.cache and (self.cache_size+matrix.nbytes>CACHE_BYTES or len(self.cache)>=256):
                    _,old=self.cache.popitem(last=False); self.cache_size-=old[1].nbytes
                self.cache[key]=value; self.cache_size+=matrix.nbytes
        return value

    def begin(self, recording, signature):
        with self.store.transaction():
            self.store.db.execute('''INSERT INTO retrieval_recordings VALUES (?,?,?,?,?,?,NULL,?)
                ON CONFLICT(id) DO NOTHING''', (recording['id'], 'service', recording['cameraId'], recording['sourceType'],
                    recording.get('recordedAt'), recording.get('duration'), json.dumps(recording)))
            self.store.db.execute('''INSERT INTO retrieval_index_jobs(recording_id,signature,status) VALUES (?,?,'indexing')
                ON CONFLICT(recording_id,signature) DO UPDATE SET status='indexing',retry_count=retry_count+1,error=NULL''',
                (recording['id'], signature))

    @staticmethod
    def unit_id(path, kind, signature):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return hashlib.sha256((signature+'|'+kind+'|'+digest).encode()).hexdigest()

    def has_unit(self, key):
        with self.store.lock:
            return self.store.db.execute('SELECT 1 FROM retrieval_units WHERE id=?', (key,)).fetchone() is not None

    def save_unit(self, key, signature, model, vector):
        blob = vector_blob(vector)
        with self.store.transaction():
            self.store.db.execute('INSERT OR IGNORE INTO retrieval_units VALUES (?,?,?,?,?)', (key, signature, model, DIMENSIONS, blob))

    def save_clip(self, clip, signature, embeddings):
        with self.store.transaction():
            self.store.db.execute('INSERT OR REPLACE INTO retrieval_clips VALUES (?,?,?,?,?,?)',
                (clip['id'], signature, clip['recordingId'], clip['start'], clip['end'], json.dumps(clip)))
            self.store.db.execute('DELETE FROM retrieval_embeddings WHERE clip_id=? AND signature=?', (clip['id'], signature))
            for kind, offset, unit_id, thumbnail in embeddings:
                self.store.db.execute('INSERT INTO retrieval_embeddings VALUES (?,?,?,?,?,?)',
                    (clip['id'], signature, kind, offset, unit_id, thumbnail))
            self.store.db.execute('''UPDATE retrieval_index_jobs SET completed_units=(
                SELECT count(*) FROM retrieval_embeddings e JOIN retrieval_clips c ON e.clip_id=c.id AND e.signature=c.signature
                WHERE c.recording_id=? AND c.signature=?) WHERE recording_id=? AND signature=?''',
                (clip['recordingId'], signature, clip['recordingId'], signature))

    def publish(self, recording, signature, expected_clips):
        with self.store.transaction():
            counts = self.store.db.execute('''SELECT c.id, sum(e.kind='video'), sum(e.kind='frame'), json_extract(c.payload,'$.expectedFrames') FROM retrieval_clips c
                JOIN retrieval_embeddings e ON e.clip_id=c.id AND e.signature=c.signature
                JOIN retrieval_units u ON u.id=e.unit_id AND u.signature=e.signature
                WHERE c.recording_id=? AND c.signature=? GROUP BY c.id''', (recording['id'], signature)).fetchall()
            if len(counts) != expected_clips or any(v != 1 or not 1 <= f <= 3 or (expected is not None and f!=expected) for _, v, f, expected in counts):
                raise ValueError('双索引尚未完整，不能发布')
            self.store.db.execute('''UPDATE retrieval_recordings SET active_signature=?,duration=?,payload=? WHERE id=?''',
                (signature, recording['duration'], json.dumps(recording), recording['id']))
            self.store.db.execute("UPDATE retrieval_index_jobs SET status='ready',error=NULL WHERE recording_id=? AND signature=?", (recording['id'], signature))
            self.store.db.execute("UPDATE retrieval_meta SET value=value+1 WHERE key='generation'")
            self.invalidate()

    def failed(self, rid, signature, status, error):
        with self.store.transaction():
            self.store.db.execute('UPDATE retrieval_index_jobs SET status=?,error=? WHERE recording_id=? AND signature=?', (status, error, rid, signature))

    def where(self, signature, cameras=None, start=None, end=None, sources=None):
        clauses = ["r.scope='service'", 'r.active_signature=?', 'c.signature=r.active_signature']
        args = [signature]
        for column, values in (('r.camera_id', cameras), ('r.source', sources)):
            if values is not None:
                if not values: clauses.append('0')
                else:
                    clauses.append(column+' IN ('+','.join('?' for _ in values)+')'); args.extend(sorted(values))
        if start is not None:
            clauses.extend(['r.recorded_at IS NOT NULL', 'r.recorded_at+c.end>?', 'r.recorded_at+c.start<?'])
            args.extend([start, end])
        return ' AND '.join(clauses), args

    def recall(self, query, signature, *, cameras=None, start=None, end=None, sources=None, limit=10):
        began = time.monotonic()
        q = np.frombuffer(vector_blob(query), dtype='<f4')
        where, params = self.where(signature, cameras, start, end, sources)
        join = ' FROM retrieval_clips c JOIN retrieval_recordings r ON r.id=c.recording_id '
        with self.store.lock:
            rows = self.store.db.execute('SELECT c.payload,r.payload'+join+' WHERE '+where, params).fetchall()
        clips = {json.loads(c)['id']: json.loads(c) | {'recording': json.loads(r)} for c, r in rows}
        if not clips: return [], dict(vectorCount=0, clipCount=0, recallMs=0)
        video, frames = {}, {}
        generation=self.generation
        cache_scope=(signature,tuple(sorted(cameras)) if cameras is not None else None,start,end,
                     tuple(sorted(sources)) if sources is not None else None)
        last, total = 0, 0
        while True:
            # Always filter metadata in SQL before fetching any vector bytes.
            def load():
                frame_scope=''
                frame_args=[]
                if start is not None:
                    frame_scope=" AND (e.kind='video' OR (r.recorded_at+e.offset_ms/1000.0>=? AND r.recorded_at+e.offset_ms/1000.0<?))"
                    frame_args=[start,end]
                with self.store.lock:
                    return self.store.db.execute('''SELECT e.rowid,e.clip_id,e.kind,e.offset_ms,e.thumbnail,u.vector'''+join+'''
                        JOIN retrieval_embeddings e ON e.clip_id=c.id AND e.signature=c.signature
                        JOIN retrieval_units u ON u.id=e.unit_id AND u.signature=e.signature
                        WHERE '''+where+frame_scope+' AND e.rowid>? ORDER BY e.rowid LIMIT ?', (*params, *frame_args, last, BLOCK_ROWS)).fetchall()
            rows,matrix=self.cached_block(generation,cache_scope,last,load)
            if not rows: break
            last = rows[-1][0]; total += len(rows)
            scores = matrix @ q
            for row, score in zip(rows, scores):
                _, clip_id, kind, offset, thumbnail = row
                if clip_id not in clips: continue  # A concurrent publication is retried by the caller.
                if kind == 'frame' and start is not None:
                    if not start <= clips[clip_id]['recording']['recordedAt'] + offset/1000 < end: continue
                target = video if kind == 'video' else frames
                frame = dict(offset=offset/1000, thumbnail=thumbnail)
                if clip_id not in target or score > target[clip_id][0]: target[clip_id] = (float(score), frame)
        return fuse(video, frames, clips, limit), dict(vectorCount=total, clipCount=len(clips), recallMs=round((time.monotonic()-began)*1000, 2),vectorCacheBytes=self.cache_size)

    def delete(self, rid):
        with self.store.transaction():
            self.store.db.execute('DELETE FROM retrieval_embeddings WHERE clip_id IN (SELECT id FROM retrieval_clips WHERE recording_id=?)', (rid,))
            self.store.db.execute('DELETE FROM retrieval_clips WHERE recording_id=?', (rid,))
            self.store.db.execute('DELETE FROM retrieval_recordings WHERE id=?', (rid,))
            self.store.db.execute('DELETE FROM retrieval_index_jobs WHERE recording_id=?', (rid,))
            self.store.db.execute('DELETE FROM retrieval_units WHERE id NOT IN (SELECT unit_id FROM retrieval_embeddings)')
            self.store.db.execute("UPDATE retrieval_meta SET value=value+1 WHERE key='generation'")
            self.invalidate()
