"""Bounded-memory recall benchmark; synthetic vectors, not semantic quality.

Run with OPENBLAS_NUM_THREADS=1 before importing NumPy. Uses a temporary SQLite
database and 10,000 vectors, two warmups and 30 measured full SQL+matrix recalls.
"""
import json, tempfile, time
try: import resource
except ImportError: resource=None
from pathlib import Path
import numpy as np
from ..store import Store
from .index_v2 import RetrievalIndex, vector_blob


def main():
    with tempfile.TemporaryDirectory(prefix='eg-recall-bench-') as directory:
        store=Store(Path(directory)/'bench.sqlite'); index=RetrievalIndex(store)
        recording=dict(id='bench',cameraId='bench-camera',sourceType='synthetic',recordedAt=1700000000,duration=50000)
        index.begin(recording,'bench'); rng=np.random.default_rng(16)
        with store.transaction():
            for i in range(2500):
                clip=dict(id=f'clip-{i}',recordingId='bench',cameraId='bench-camera',continuityId='bench',start=i*15,end=i*15+20)
                entries=[]
                for j in range(4):
                    key=f'{i}-{j}'; kind='video' if j==0 else 'frame'
                    store.db.execute('INSERT INTO retrieval_units VALUES (?,?,?,?,?)',(key,'bench','synthetic',1024,vector_blob(rng.normal(size=1024))))
                    entries.append((kind,-1 if j==0 else (i*15+j*5)*1000,key,None))
                index.save_clip(clip,'bench',entries)
            index.publish(recording,'bench',2500)
        q=rng.normal(size=1024); durations=[]
        for run in range(32):
            began=time.perf_counter(); hits,metrics=index.recall(q,'bench',cameras={'bench-camera'})
            elapsed=(time.perf_counter()-began)*1000
            if run>=2: durations.append(elapsed)
        print(json.dumps(dict(syntheticOnly=True,vectorCount=metrics['vectorCount'],clipCount=metrics['clipCount'],runs=len(durations),
            p50Ms=round(float(np.percentile(durations,50)),2),p95Ms=round(float(np.percentile(durations,95)),2),
            maxRSSKiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss if resource else None,
            vectorCacheMiB=round(index.cache_size/(1024*1024),2),blockRows=1024)))
        store.close()


if __name__=='__main__': main()
