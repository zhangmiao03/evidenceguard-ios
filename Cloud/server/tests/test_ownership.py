import asyncio
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from evidenceguard.app import create_app
from evidenceguard.store import Store, CameraConflict
from evidenceguard.camera.contracts import DeviceManifest, CapabilityState, FrameRef, SnapshotKind, SnapshotReceipt, CameraCommandContext
from evidenceguard.camera.registry import CameraRegistry, RoutedCameraAdapter
from evidenceguard.camera.adapters.eufy_ports import EufyT8171Adapter, EufyT8214Adapter
from evidenceguard.camera.service import CameraService
from evidenceguard.harness.scheduler import TaskScheduler
from evidenceguard.harness.tools import build_tools
from evidenceguard.harness.runtime import AgentRuntime
from evidenceguard.worker import ObservationWorker
from test_harness import ScriptedProvider, tool, settle


@pytest.fixture
def store(tmp_path):
    s=Store(tmp_path/'ownership.sqlite')
    yield s
    s.close()


def active(s, devices, name='守护'):
    draft=s.create_draft('看住测试物品',devices,name=name)
    return s.confirm(draft['id'],1)


def consent(s, draft):
    return {c['skillId']:c['executionEpoch'] for c in s.conflicts(draft)}


def manifests():
    return [DeviceManifest(d,m,d,'primary','online','fixture-lab/v1',(),{'liveSnapshot':CapabilityState.SUPPORTED},'fixture')
            for d,m in [('cam-a','T8171'),('cam-b','T8214')]]


def cameras():
    camera=AsyncMock()
    camera.live=None  # Fixture cameras do not expose a mobile foreground relay.
    camera.manifests.return_value=manifests()
    camera.frame_bytes.return_value=(b'test-image','image/jpeg')
    camera.snapshot.side_effect=lambda d,k,*args: SnapshotReceipt('sdk-receipt','completed',k,
        FrameRef('frame-'+d,d,'main',time.time(),time.time(),'fixture','live','1'),'新画面')
    return camera


def test_two_cameras_independent_and_dual_switch_is_atomic(store):
    a=active(store,['cam-a'],'A守护'); b=active(store,['cam-b'],'B守护')
    dual=store.create_draft('双摄守护',['cam-a','cam-b'])
    with pytest.raises(CameraConflict) as error: store.confirm(dual['id'],1)
    assert {c['skillId'] for c in error.value.conflicts}=={a['id'],b['id']}
    with pytest.raises(CameraConflict): store.confirm(dual['id'],1,{a['id']:a['executionEpoch']})
    assert store.owner('cam-a')['id']==a['id'] and store.owner('cam-b')['id']==b['id']
    store.confirm(dual['id'],1,consent(store,dual))
    assert store.skill(a['id'])['status']==store.skill(b['id'])['status']=='paused'
    assert store.owner('cam-a')['id']==store.owner('cam-b')['id']==dual['id']
    with pytest.raises(CameraConflict): store.lifecycle(a['id'],'resume')
    store.lifecycle(a['id'],'resume',consent(store,a))
    assert store.owner('cam-a')['id']==a['id'] and store.owner('cam-b') is None
    assert store.skill(dual['id'])['status']=='paused'


def test_stale_switch_consent_does_not_pause_a_new_execution(store):
    a=active(store,['cam-a']); b=store.create_draft('另一任务',['cam-a'])
    old_consent=consent(store,b)
    store.lifecycle(a['id'],'pause'); resumed=store.lifecycle(a['id'],'resume')
    assert a['executionEpoch']!=resumed['executionEpoch']
    with pytest.raises(CameraConflict): store.confirm(b['id'],1,old_consent)
    assert store.owner('cam-a')['id']==a['id'] and store.skill(b['id'])['status']=='draft'


def test_resume_drops_pre_pause_trigger_baseline_and_stale_worker_write(store):
    a=active(store,['cam-a']); stale=dict(a)
    a['evaluation']={'armed':True,'position':'inside','episode':3,'candidate':{'count':2}}
    store.save_skill(a); store.lifecycle(a['id'],'pause')
    worker=ObservationWorker(store,AsyncMock())
    worker.evaluate(stale,[],time.time())
    assert store.skill(a['id'])['status']=='paused'
    resumed=store.lifecycle(a['id'],'resume')
    assert resumed['evaluation']=={'episode':3}
    assert resumed['executionEpoch']!=a['executionEpoch']
    worker.evaluate(stale,[],time.time())
    assert store.skill(a['id'])['executionEpoch']==resumed['executionEpoch']


def test_simultaneous_activation_across_db_connections_has_one_winner(tmp_path):
    path=tmp_path/'concurrent.sqlite'; first=Store(path); second=Store(path)
    a=first.create_draft('第一项',['cam-a']); b=first.create_draft('第二项',['cam-a'])
    barrier=threading.Barrier(2)
    def activate(s,d):
        barrier.wait()
        try: s.confirm(d['id'],1); return True
        except CameraConflict: return False
    with ThreadPoolExecutor(2) as pool:
        jobs=[pool.submit(activate,first,a),pool.submit(activate,second,b)]
        assert sum(j.result() for j in jobs)==1
    assert len([s for s in first.skills() if s['status']=='active'])==1
    first.close(); second.close()


def test_legacy_overlap_recovery_pauses_all_conflicting_tasks(store):
    a=store.create_draft('旧任务一',['cam-a']); b=store.create_draft('旧任务二',['cam-a','cam-b'])
    with store.transaction():
        for s in [a,b]:
            s['status']='active'
            store.db.execute('UPDATE skills SET payload=? WHERE id=?',(json.dumps(s),s['id']))
    store.recover_ownership()
    assert all(s['status']=='paused' for s in store.skills())
    assert store.owner('cam-a') is None and store.owner('cam-b') is None


def test_inflight_capture_drains_before_switch_and_old_queue_is_fenced(store):
    async def check():
        a=active(store,['cam-a']); b=store.create_draft('新任务',['cam-a'])
        scheduler=TaskScheduler(); camera=cameras(); service=CameraService(store,camera,scheduler)
        entered=asyncio.Event(); release=asyncio.Event(); waiting=asyncio.Event()
        async def blocking(d,k,context):
            assert context.owner_id==a['id'] and context.execution_epoch==a['executionEpoch']
            entered.set(); await release.wait()
            return SnapshotReceipt('receipt','completed',k,FrameRef('frame',d,'main',time.time(),time.time(),'fixture','live','1'),'新图')
        camera.snapshot.side_effect=blocking
        capture=asyncio.create_task(service.capture('cam-a',a['id']))
        await entered.wait()
        async def switch():
            waiting.set()
            async with service.transition(): store.confirm(b['id'],1,consent(store,b))
        swap=asyncio.create_task(switch()); await waiting.wait(); await asyncio.sleep(0)
        # Queued after switch requested: remembers the old epoch, but cannot use it later.
        queued=asyncio.create_task(service.capture('cam-a',a['id'])); await asyncio.sleep(0)
        assert store.owner('cam-a')['id']==a['id'] and not swap.done()
        release.set()
        assert (await capture)['status']=='completed'
        await swap
        assert (await queued)['status']=='failed'
        assert camera.snapshot.await_count==1 and store.owner('cam-a')['id']==b['id']
        await scheduler.shutdown()
    asyncio.run(check())


def test_generic_chat_joins_owner_but_paused_skill_cannot_capture(store):
    async def check():
        a=active(store,['cam-a']); camera=cameras(); scheduler=TaskScheduler()
        service=CameraService(store,camera,scheduler)
        with pytest.raises(CameraConflict): await service.capture('cam-a')
        receipt=await build_tools(store,camera,service,camera_id='cam-a').call('request_camera_snapshot')
        assert receipt['skillId']==a['id'] and receipt['status']=='completed'
        store.lifecycle(a['id'],'pause')
        with pytest.raises(ValueError): await service.capture('cam-a',a['id'])
        await scheduler.shutdown()
    asyncio.run(check())


def test_history_scopes_saved_media_and_never_calls_camera(store):
    async def check():
        a=active(store,['cam-a','cam-b']); camera=AsyncMock()
        for d,t in [('cam-a',100),('cam-b',200)]:
            frame=dict(device_id=d,frame_id=d+'-saved',captured_at=t)
            media=store.save_media(frame,b'saved-image','image/jpeg')
            store.save_evidence(a,dict(**frame,source_type='fixture',imageUrl=media['imageUrl'],mediaStatus='saved'))
        tools=build_tools(store,camera,skill_id=a['id'],camera_id='cam-a',execution_mode='history')
        assert set(tools.names)=={'search_evidence','read_stored_image','list_camera_events'}
        for name in ['request_camera_snapshot','request_recheck','draft_visual_skill','list_camera_capabilities']:
            with pytest.raises(ValueError): await tools.call(name)
        result=await tools.call('search_evidence',start_at=90,end_at=110)
        assert len(result['items'])==1 and result['availableRange']=={'from':100,'to':100}
        receipt=await tools.call('read_stored_image',evidence_id=result['items'][0]['id'])
        assert receipt['historical'] is True and receipt['capturedAt']==100
        with pytest.raises(ValueError): await tools.call('read_stored_image',evidence_id=a['id']+':cam-b-saved')
        assert (await tools.call('search_evidence',start_at=300))['items']==[]
        assert camera.mock_calls==[] and store.skill(a['id'])['status']=='active'
    asyncio.run(check())


def test_history_model_cannot_call_live_tools_even_if_it_asks(store):
    async def check():
        camera=cameras()
        provider=ScriptedProvider([tool('request_camera_snapshot',{}),{'role':'assistant','content':'请切换实时守护。'}])
        runtime=AgentRuntime(store,build_tools(store,camera),provider,camera)
        result=await settle(runtime,runtime.start('现在拍照','history',camera_id='cam-a',execution_mode='history'))
        assert result['status']=='completed' and result['toolReceipts'][0]['status']=='failed'
        camera.snapshot.assert_not_called()
        with pytest.raises(ValueError): runtime.start('查询','history',execution_mode='live')
        with pytest.raises(ValueError): runtime.start('现在拍照','history',request_id=result['id'],camera_id='cam-a',execution_mode='live')
        await runtime.scheduler.shutdown()
    asyncio.run(check())


def test_history_relative_date_is_calculated_on_server(store):
    async def check():
        from datetime import datetime
        from zoneinfo import ZoneInfo
        a=active(store,['cam-a']); now=time.time()
        store.save_evidence(a,dict(device_id='cam-a',frame_id='today',captured_at=now,relation='inside'))
        tools=build_tools(store,AsyncMock(),execution_mode='history')
        result=await tools.call('search_evidence',period='today')
        assert result['count']==1 and result['countsByRelation']=={'inside':1}
        assert result['items'][0]['capturedAtText'].startswith(datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d'))
        midnight=datetime.fromtimestamp(result['requestedRange']['from'],ZoneInfo('Asia/Shanghai'))
        assert midnight.hour==midnight.minute==midnight.second==0
        assert (await tools.call('search_evidence',period='yesterday'))['count']==0
        with pytest.raises(ValueError): await tools.call('search_evidence',period='today',start_at=now)
    asyncio.run(check())


def test_history_lane_runs_while_live_chat_is_busy(store):
    async def check():
        gate=asyncio.Event(); entered=asyncio.Event(); provider=ScriptedProvider([])
        async def respond(messages,schemas):
            if schemas and {s['function']['name'] for s in schemas} <= {'search_evidence','read_stored_image','search_recordings','list_camera_events'}:
                return {'role':'assistant','content':'历史分析'}
            entered.set(); await gate.wait(); return {'role':'assistant','content':'实时对话'}
        provider.complete.side_effect=respond
        scheduler=TaskScheduler({'chat':1,'history':2,'camera':2,'observation':1})
        camera=cameras(); runtime=AgentRuntime(store,build_tools(store,camera),provider,camera,scheduler)
        live=runtime.start('实时','live'); await entered.wait()
        h1=runtime.start('回顾','h1',execution_mode='history'); h2=runtime.start('回顾','h2',execution_mode='history')
        await asyncio.wait_for(asyncio.gather(runtime.tasks[h1['id']],runtime.tasks[h2['id']]),2)
        assert store.run(h1['id'])['status']==store.run(h2['id'])['status']=='completed'
        assert store.run(live['id'])['status']=='running'
        gate.set(); await runtime.shutdown(); await scheduler.shutdown()
    asyncio.run(check())


def test_official_sdk_ports_route_both_models_with_ownership_context():
    async def check():
        bridge=AsyncMock()
        async def manifest(d,m): return next(v for v in manifests() if v.id==d and v.model==m)
        bridge.manifest.side_effect=manifest
        registry=CameraRegistry(RoutedCameraAdapter({'cam-a':EufyT8171Adapter(bridge),'cam-b':EufyT8214Adapter(bridge)}))
        assert {m.model for m in await registry.manifests()}=={'T8171','T8214'}
        context=CameraCommandContext('request','owner','epoch',time.time()+8)
        for d in ['cam-a','cam-b']:
            await registry.snapshot(d,SnapshotKind.LIVE,context)
            bridge.snapshot.assert_awaited_with(d,SnapshotKind.LIVE,context)
            with pytest.raises(ValueError): await registry.snapshot(d,SnapshotKind.LIVE)
        bridge.manifest.side_effect=lambda d,m: manifests()[1]
        with pytest.raises(ValueError): await registry.manifests()
    asyncio.run(check())


def test_api_conflict_payload_confirm_switch_and_resume(tmp_path):
    camera=cameras()
    async def state():
        return {'cameras':[dict(id=d,observation=dict(marker_ids=[17],bbox=[.38,.44,.46,.54],captured_at=time.time(),revision=1,frame_id=d+'-1')) for d in ['cam-a','cam-b']]}
    camera.state.side_effect=state
    app=create_app(tmp_path/'api.sqlite',start_worker=False,camera_adapter=camera,provider=type('Off',(),{'ready':False,'name':'off'})())
    with TestClient(app) as client:
        store=app.state.store; a=active(store,['cam-a','cam-b']); b=store.create_draft('另一个任务',['cam-a'],rules={'taskKind':'marker_region'})
        response=client.post('/api/skills/'+b['id']+'/confirm',json={'revision':1,'fixtureAcknowledged':True})
        assert response.status_code==409 and response.json()['code']=='camera_occupied'
        assert response.json()['conflicts'][0]['skillId']==a['id']
        response=client.post('/api/skills/'+b['id']+'/confirm',json={'revision':1,'fixtureAcknowledged':True,'switchFrom':consent(store,b)})
        assert response.status_code==200 and store.owner('cam-b') is None
        response=client.post('/api/skills/'+a['id']+'/lifecycle',json={'action':'resume'})
        assert response.status_code==409
        response=client.post('/api/skills/'+a['id']+'/lifecycle',json={'action':'resume','switchFrom':consent(store,a)})
        assert response.status_code==200 and store.owner('cam-a')['id']==store.owner('cam-b')['id']==a['id']
