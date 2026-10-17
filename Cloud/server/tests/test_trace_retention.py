import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from evidenceguard.ops import Recorder
from evidenceguard.display_receipts import install


class CriticalRetentionTests(unittest.TestCase):
    def test_polling_eviction_keeps_agent_steps_and_backfills_remaining_history(self):
        with tempfile.TemporaryDirectory() as folder:
            r=Recorder(Path(folder)/'ops.db',capacity=1024,retention=100)
            try:
                for i,name in enumerate(['request.snapshot','tool.started','tool.finished','agent.result']):
                    r.emit(name,kind='prompt' if i==0 else 'event',trace={'traceId':'task'},data={'text':'preserved'})
                for i in range(250):r.emit('api.completed',source='client',data={'route':'poll'})
                self.assertTrue(r.flush());self.assertEqual(r.write_errors,0)
                with r.lock:
                    self.assertEqual(r.db.execute('SELECT count(*) FROM records').fetchone()[0],100)
                    self.assertEqual(r.db.execute('SELECT count(*) FROM critical_records').fetchone()[0],4)
            finally:r.close()
            again=Recorder(Path(folder)/'ops.db')
            try:
                self.assertTrue(again.flush())
                with again.lock:self.assertEqual(again.db.execute('SELECT count(*) FROM critical_records').fetchone()[0],4)
            finally:again.close()

    def test_critical_cap_removes_whole_old_trace(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'EG_OPS_CRITICAL_RECORDS':'100'}):
            r=Recorder(Path(folder)/'ops.db',capacity=512)
            try:
                for i in range(60):r.emit('tool.finished',trace={'traceId':'old-task'})
                for i in range(60):r.emit('tool.finished',trace={'traceId':'new-task'})
                self.assertTrue(r.flush());self.assertEqual(r.write_errors,0)
                with r.lock:
                    groups=r.db.execute('SELECT trace_id,count(*) FROM critical_records GROUP BY trace_id').fetchall()
                    self.assertEqual(groups,[('new-task',60)])
            finally:r.close()

    def test_display_receipts_accept_hashes_only_and_never_change_business_state(self):
        with tempfile.TemporaryDirectory() as folder:
            r=Recorder(Path(folder)/'ops.db');app=FastAPI();install(app,SimpleNamespace(ops=r))
            c=TestClient(app);payload=dict(id='event-1',runId='run-1',backendTextHash=hashlib.sha256('原文'.encode()).hexdigest(),displayTextHash='a'*64,presentationVersion='v1',appVersion='1/17',platform='ios',status='completed')
            try:
                self.assertEqual(c.post('/api/ops/display-receipts',json=payload).status_code,422)
                headers={'X-EG-Installation-ID':'test-installation'}
                self.assertEqual(c.post('/api/ops/display-receipts',json={**payload,'body':'must not store'},headers=headers).status_code,422)
                self.assertEqual(c.post('/api/ops/display-receipts',json=payload,headers=headers).json()['accepted'],1)
                payload['id']='event-2';payload['backendTextHash']='b'*64
                self.assertEqual(c.post('/api/ops/display-receipts',json=payload,headers=headers).status_code,200)
                self.assertTrue(r.flush())
                with r.lock:rows=[json.loads(x[0]) for x in r.db.execute('SELECT payload FROM critical_records')]
                self.assertEqual(len(rows),2);self.assertEqual(rows[-1]['data']['backendTextHash'],'b'*64)
                self.assertEqual(rows[-1]['source'],'client')
            finally:r.close()

if __name__=='__main__':unittest.main()
