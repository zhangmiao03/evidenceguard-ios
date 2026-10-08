import asyncio
import base64
import copy
import time
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
from evidenceguard.store import Store
from evidenceguard.worker import ObservationWorker
from evidenceguard.camera.contracts import DeviceManifest, CapabilityState, FrameRef, SnapshotKind, SnapshotReceipt
from evidenceguard.camera.registry import CameraRegistry
from evidenceguard.camera.service import CameraService
from evidenceguard.harness.scheduler import TaskEnvelope, TaskScheduler
from evidenceguard.harness.tools import build_tools
from evidenceguard.harness.runtime import AgentRuntime

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j1ioAAAAASUVORK5CYII=')

@pytest.fixture
def env(tmp_path):
    store = Store(tmp_path/'state.sqlite')
    cameras=AsyncMock()
    worker=ObservationWorker(store,cameras)
    s=store.create_draft('看住测试目标',['cam-a','cam-b'])
    s=store.confirm(s['id'],1)
    yield store,worker,s,time.time()+.1
    store.close()


def frame(camera,at,relation='inside',revision=1,frame_id=None):
    bbox={'inside':[.38,.44,.46,.54], 'outside':[.84,.4,.93,.54], 'boundary':[.63,.4,.68,.54], 'unknown':None}[relation]
    return dict(id=camera,transport_online=True,observation=dict(frame_id=frame_id or f'{camera}-1-{int(at*1000)}',device_id=camera,
                captured_at=at,received_at=at,revision=revision,channel_id='main',source_type='fixture',marker_ids=[17] if bbox else [],bbox=bbox))


def feed(env,relations,start,n=3):
    store,w,s,_=env
    for i in range(n):
        t=start+i*3.2
        w.evaluate(store.skill(s['id']),[frame(d,t,r) for d,r in zip(['cam-a','cam-b'],relations)],t)
    return store.skill(s['id'])


def test_outside_at_start_is_not_a_leave_event(env):
    store,w,s,t=env
    result=feed(env,['outside','outside'],t,5)
    assert result['result']=='unknown'
    assert result['alert']=='none'
    assert not any(e['type']=='alert_opened' for e in store.events(s['id']))


def test_transition_once_occlusion_acknowledgement_and_recovery(env):
    store,w,s,t=env
    assert feed(env,['inside','inside'],t)['result']=='confirmed'
    result=feed(env,['outside','outside'],t+12.0,7)
    assert result['result']=='needs_attention' and result['status']=='active'
    assert len([e for e in store.events(s['id']) if e['type']=='alert_opened'])==1
    assert feed(env,['unknown','unknown'],t+40.0)['result']=='unknown'
    store.recheck(s['id'],True)
    result=feed(env,['outside','outside'],t+52.0)
    assert result['result']=='needs_attention' and result['alert']=='acknowledged'
    result=feed(env,['inside','inside'],t+68.0)
    assert result['result']=='confirmed' and result['alert']=='resolved'
    result=feed(env,['outside','outside'],t+84.0)
    assert result['evaluation']['episode']==2


def test_duplicate_boundary_and_stale_frames_cannot_complete_confirmation(env):
    store,w,s,t=env
    repeated=[frame('cam-a',t),frame('cam-b',t)]
    for i in range(5): w.evaluate(store.skill(s['id']),repeated,t+i*.1)
    assert store.skill(s['id'])['result']=='unknown'
    feed(env,['inside','inside'],t+4.0,1)
    feed(env,['boundary','boundary'],t+7.2,1)
    assert feed(env,['inside','inside'],t+10.4,1)['result']=='unknown'
    assert feed(env,['inside','inside'],t+13.6,2)['result']=='confirmed'
    assert w.evaluate(store.skill(s['id']),repeated,t+60.0)['result']=='unknown'


def test_conflict_secondary_view_and_camera_revision(env):
    store,w,s,t=env
    feed(env,['inside','inside'],t)
    assert feed(env,['inside','outside'],t+12.0)['result']=='unknown'
    assert feed(env,['unknown','inside'],t+24.0)['result']=='confirmed'
    changed=[frame('cam-a',t+40.0,revision=2),frame('cam-b',t+40.0,revision=2)]
    assert w.evaluate(store.skill(s['id']),changed,t+40.0)['result']=='unknown'


def test_one_shot_and_restart_do_not_duplicate_alert(env):
    store,w,s,t=env
    feed(env,['inside','inside'],t)
    feed(env,['outside','outside'],t+12.0)
    restarted=ObservationWorker(store,w.cameras)
    for i in range(4):
        at=t+28.0+i*4
        restarted.evaluate(store.skill(s['id']),[frame('cam-a',at,'outside'),frame('cam-b',at,'outside')],at)
    assert len([e for e in store.events(s['id']) if e['type']=='alert_opened'])==1
    store.lifecycle(s['id'],'pause')
    other=store.create_draft('一次性测试',['cam-a'],rules={'completion':'once'})
    other=store.confirm(other['id'],1)
    for i in range(6):
        at=t+60.0+i*4
        w.evaluate(store.skill(other['id']),[frame('cam-a',at,'inside' if i<3 else 'outside')],at)
    assert store.skill(other['id'])['status']=='completed'


def test_task_regions_are_independent(env):
    store,w,s,t=env
    other=store.create_draft('独立区域',['cam-a'])
    other['regions']['cam-a']={'x':.75,'y':.1,'width':.24,'height':.8}
    store.save_skill(other)
    assert feed(env,['inside','inside'],t)['result']=='confirmed'
    store.lifecycle(s['id'],'pause')
    other=store.confirm(other['id'],1)
    for i in range(3): w.evaluate(store.skill(other['id']),[frame('cam-a',t+i*3.2)],t+i*3.2)
    assert store.skill(other['id'])['result']=='unknown' # inside A is outside B, with no preceding baseline.


def test_evidence_bytes_survive_source_loss_and_restart(env):
    async def check():
        store,w,s,t=env
        w.cameras.frame_bytes.return_value=(PNG,'image/png')
        feed(env,['inside','inside'],t)
        await w.persist_evidence()
        item=next(e for e in store.evidence() if e['relation']=='inside')
        assert item['imageUrl'].startswith('/api/media/')
        key=item['imageUrl'].rsplit('/',1)[1]
        w.cameras.frame_bytes.side_effect=RuntimeError('source evicted')
        assert store.media(key)[0]==PNG
        assert store.media(key)[2]['frame']['device_id']==item['cameraId']
        from pathlib import Path
        reopened=Store(Path(store.db.execute('PRAGMA database_list').fetchone()[2]))
        assert reopened.media(key)[0]==PNG
        reopened.close()
    asyncio.run(check())


def test_scoped_tools_reject_wrong_task_and_preserve_revision_geometry(env):
    async def check():
        store,w,s,t=env
        other=store.create_draft('另一个任务',['cam-b'])
        w.cameras.manifests.return_value=[DeviceManifest(d,d,d,'primary','online','test',(),{},'test') for d in ['cam-a','cam-b']]
        scoped=build_tools(store,w.cameras,skill_id=s['id'],camera_id='cam-a')
        with pytest.raises(ValueError): await scoped.call('get_task_state',skill_id=other['id'])
        assert len(await scoped.call('list_tasks'))==1
        source=store.skill(s['id']); source['target']['box']['x']=.3; store.save_skill(source)
        draft=await scoped.call('draft_visual_skill',prompt='调整为进入时提醒',devices=['cam-a','cam-b'],name='新版',target_description='测试物',rules={'trigger':'enters_region'})
        assert draft['replacesId']==s['id']
        assert draft['regions']==source['regions']
        assert draft['target']['box']==source['target']['box']
        assert store.skill(s['id'])['status']=='active'
        store.confirm(draft['id'],1)
        assert store.skill(s['id'])['status']=='stopped'
    asyncio.run(check())


def test_snapshot_receipt_stored_and_wrong_camera_blocked(env):
    async def check():
        store,w,s,t=env
        scheduler=TaskScheduler()
        cameras=w.cameras
        cameras.manifests.return_value=[DeviceManifest('cam-a','test','test','primary','online','fixture',(),{'liveSnapshot':CapabilityState.SUPPORTED},'test')]
        now=time.time()
        f=FrameRef('cam-a-1-1','cam-a','main',now,now,'fixture','live','view-1')
        cameras.snapshot.side_effect=lambda *args: SnapshotReceipt('request-1','completed',SnapshotKind.LIVE,replace(f,captured_at=time.time()),'取得新图')
        cameras.frame_bytes.return_value=(PNG,'image/png')
        service=CameraService(store,cameras,scheduler)
        scoped=build_tools(store,cameras,service,s['id'],'cam-a')
        capture=await scoped.call('request_camera_snapshot')
        assert capture['status']=='completed' and store.media(capture['mediaId'])[0]==PNG
        with pytest.raises(ValueError): await scoped.call('request_camera_snapshot',device_id='cam-other')
        cameras.snapshot.side_effect=None
        cameras.snapshot.return_value=SnapshotReceipt('request-2','completed',SnapshotKind.LIVE,replace(f,captured_at=now-20),'旧图')
        assert (await service.capture('cam-a',s['id']))['status']=='failed'
        await scheduler.shutdown()
    asyncio.run(check())


def test_scheduler_separates_camera_and_chat_and_bounds_concurrency():
    async def check():
        scheduler=TaskScheduler({'chat':1,'camera':1},capacity=3)
        gate=asyncio.Event(); started=asyncio.Event(); order=[]
        async def block(): started.set(); await gate.wait()
        async def next_chat(): order.append('chat')
        first=scheduler.submit(TaskEnvelope('a','chat'),block)
        await started.wait()
        queued=scheduler.submit(TaskEnvelope('b','chat'),next_chat)
        camera=scheduler.submit(TaskEnvelope('c','camera'),lambda: asyncio.sleep(0,result='frame'))
        assert await camera=='frame' and order==[]
        gate.set(); await first; await queued
        assert order==['chat']
        await scheduler.shutdown()
    asyncio.run(check())
