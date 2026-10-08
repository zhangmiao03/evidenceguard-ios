import asyncio
import signal
import sys
from dataclasses import asdict
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.domain import new_task, evaluate, Observation
from backend.storage import Store
from backend.simulator import stop_process


def test_restart_retains_alert_without_treating_stored_state_as_current(tmp_path):
    store=Store(tmp_path)
    task=new_task(100)
    for t in (101,102):
        o=Observation(f'cam-a-1-{t}','cam-a',t,t,1,'outside','test')
        events=evaluate(task,{'cam-a':o},t)
        store.save(task,{'scenario':'normal','mode':'continuous'},events)
    store.close()
    with TestClient(create_app(tmp_path,False)) as client:
        state=client.get('/api/state').json()
        assert state['task']['result']=='unknown'
        assert state['task']['alert']=='open'
        assert state['task']['episode']==1
        events=client.get('/api/events').json()
        assert sum(e['type']=='alert_opened' for e in events)==1


def test_pruning_keeps_event_evidence_and_latest_frame(tmp_path):
    store=Store(tmp_path)
    for name in ['referenced','latest','unreferenced']:
        store.frame(name,{'captured_at':1})
        (store.images/f'{name}.jpg').write_bytes(b'test')
    store.append({'evidence':[{'frame_id':'referenced'}]})
    store.prune_unreferenced(100,{'latest'})
    assert (store.images/'referenced.jpg').exists()
    assert (store.images/'latest.jpg').exists()
    assert not (store.images/'unreferenced.jpg').exists()
    store.close()


def test_shutdown_is_bounded_even_if_child_ignores_termination():
    async def run():
        script='import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print("ready",flush=True); time.sleep(100)'
        p=await asyncio.create_subprocess_exec(sys.executable,'-c',script,stdout=asyncio.subprocess.PIPE)
        assert await p.stdout.readline()==b'ready\n'
        await asyncio.wait_for(stop_process(p),4)
        assert p.returncode is not None
    asyncio.run(run())
