import asyncio,json,time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from contextlib import asynccontextmanager
import httpx,pytest
from evidenceguard.store import Store,CameraConflict
from evidenceguard.replay import ReplayWorker
from evidenceguard.video.providers import VideoProviderError,LiteVideoProvider

class Captures:
    def __init__(self,root): self.root=root;self.windows=[];self.samples=[]
    @asynccontextmanager
    async def transition(self):yield
    async def replay_sample(self,skill,at):
        self.samples.append(at)
        path=self.root/f'sample-{at}.jpg';path.write_bytes(b'jpeg')
        return SimpleNamespace(path=path)
    async def replay_window(self,skill,start,end):
        path=self.root/f'{start}-{end}.mp4';path.write_bytes(b'0123456789')
        w=SimpleNamespace(device_id='cam-a',recording_id='video-a',start=start,end=end,path=path)
        self.windows.append(w);return w

class Vision:
    async def observe_frame(self,path,query,reference=None):
        at=float(path.stem.split('-')[1])
        return dict(state='present' if at<6 else 'absent',summary='test')

def setup(tmp_path):
    store=Store(tmp_path/'db.sqlite');captures=Captures(tmp_path)
    videos=SimpleNamespace(db=SimpleNamespace(recording=lambda _:dict(duration=20,recordedAt=None)),vision=Vision())
    worker=ReplayWorker(store,videos,captures)
    s=store.create_draft('看住包裹',['cam-a']);s['replay']={'recordingId':'video-a'};s['replayState']={'cursor':0,'online':True,'generation':0};store.save_skill(s)
    store.confirm(s['id'],s['revision']);return store,worker,captures,s['id']

def test_ordered_replay_requires_baseline_and_repeated_match_and_saves_only_arrived_video(tmp_path):
    async def check():
        store,worker,captures,sid=setup(tmp_path)
        for _ in range(4):await worker.advance(store.skill(sid),0)
        assert store.skill(sid)['alert']=='none'  # absent at 6 and 9 spans only 3 s
        await worker.advance(store.skill(sid),0)
        s=store.skill(sid);assert s['alert']=='open' and s['status']=='completed'
        assert captures.samples==[0,3,6,9,12]
        assert [w.end for w in captures.windows]==[12]
        e=store.evidence()[0];assert e['clipEnd']==12 and e['originalEventTime']==12 and e['sourceType']=='replay'
        assert len([e for e in store.events(sid) if e['type']=='alert_opened'])==1
        await worker.advance(s,0);assert len(store.evidence())==1
        store.close()
    asyncio.run(check())

def test_occlusion_and_model_errors_never_open_alert(tmp_path):
    async def check():
        store,worker,_,sid=setup(tmp_path)
        worker.videos.vision.observe_frame=AsyncMock(side_effect=[dict(state='unknown',summary='遮挡')]+[VideoProviderError('output_validation','无有效结果',[])]*3)
        for _ in range(4):await worker.advance(store.skill(sid),0)
        s=store.skill(sid);assert s['alert']=='none' and s['status']=='paused' and not store.evidence()
        assert len([e for e in store.events(sid) if e['type']=='replay_model_failed'])==3
        store.close()
    asyncio.run(check())

@pytest.mark.parametrize('interrupt',['pause','disconnect','switch'])
def test_late_observation_cannot_alert_after_pause_disconnect_or_switch(tmp_path,interrupt):
    async def check():
        store,worker,_,sid=setup(tmp_path);entered=asyncio.Event();release=asyncio.Event()
        async def wait(*args):entered.set();await release.wait();return dict(state='present',summary='test')
        worker.videos.vision.observe_frame=wait
        job=asyncio.create_task(worker.advance(store.skill(sid),0));await entered.wait()
        if interrupt=='pause':store.lifecycle(sid,'pause')
        elif interrupt=='disconnect':await worker.transport(sid,False)
        else:
            new=store.create_draft('另一个任务',['cam-a'])
            with pytest.raises(CameraConflict):store.confirm(new['id'],new['revision'])
            store.confirm(new['id'],new['revision'],{sid:store.skill(sid)['executionEpoch']})
        release.set();await job
        assert store.skill(sid)['replayState']['cursor']==0 and not store.evidence()
        store.close()
    asyncio.run(check())

def test_resume_discards_baseline_and_restart_pauses_replay(tmp_path):
    async def check():
        store,worker,_,sid=setup(tmp_path)
        await worker.advance(store.skill(sid),0);assert store.skill(sid)['evaluation']['armed']
        store.lifecycle(sid,'pause');store.lifecycle(sid,'resume')
        seen=[]
        async def verify(path,query,duration):seen.append(query);return dict(state='unknown',summary='遮挡')
        worker.videos.vision.observe_frame=verify;await worker.advance(store.skill(sid),0)
        assert worker.store.skill(sid)['evaluation'].get('armed') == False and store.skill(sid)['alert']=='none'
        ReplayWorker(store,worker.videos,worker.camera_service)
        assert store.skill(sid)['status']=='paused'
        store.close()
    asyncio.run(check())

def test_video_failure_diagnostics_distinguish_transport_http_and_validation(tmp_path,monkeypatch):
    async def check():
        monkeypatch.setenv('EG_MODEL_BASE_URL','https://model.test');monkeypatch.setenv('EG_MODEL_ID','lite');monkeypatch.setenv('EG_MODEL_API_KEY','test')
        path=tmp_path/'test.mp4';path.write_bytes(b'video');original=httpx.AsyncClient
        cases=[('http',lambda r:httpx.Response(429)),('output_validation',lambda r:httpx.Response(200,json={'choices':[{'finish_reason':'length','message':{'content':'{"truncated":'}}]}))]
        for code,handler in cases:
            monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handler)))
            with pytest.raises(VideoProviderError) as error:await LiteVideoProvider().verify(path,'包裹',8)
            assert error.value.code==code and error.value.diagnostics[0]['latencySeconds']>=0
            if code=='output_validation':assert len(error.value.diagnostics)==2 and error.value.diagnostics[0]['finishReason']=='length'
    asyncio.run(check())

@pytest.mark.parametrize('reported,accepted',[(29.582,True),(30,False)])
def test_video_duration_rounding_tolerance_is_bounded_and_audited(tmp_path,monkeypatch,reported,accepted):
    async def check():
        monkeypatch.setenv('EG_MODEL_BASE_URL','https://model.test');monkeypatch.setenv('EG_MODEL_ID','lite');monkeypatch.setenv('EG_MODEL_API_KEY','test')
        path=tmp_path/'test.mp4';path.write_bytes(b'video');original=httpx.AsyncClient
        def response(request):
            body=json.loads(request.content)
            assert '29.581995000' in body['messages'][1]['content'][0]['text']
            content=dict(verdict='uncertain',summary='遮挡',eventTime=None,actionVisibility='unclear',events=[dict(action='other',start=0,end=reported,description='遮挡')])
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(content)}}]})
        monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(response)))
        if accepted:
            result=await LiteVideoProvider().verify(path,'包裹',29.581995)
            assert result['events'][0]['end']==29.581995
            assert result['diagnostics'][0]['timeQuantizationAdjusted'][0]['reported']==reported
        else:
            with pytest.raises(VideoProviderError) as error:await LiteVideoProvider().verify(path,'包裹',29.581995)
            assert len(error.value.diagnostics)==2
    asyncio.run(check())

def test_replay_adapter_excludes_future_frames_and_checks_device(tmp_path):
    import subprocess
    from evidenceguard.camera.adapters.replay import ReplayAdapter
    async def check():
        source=tmp_path/'source.mp4'
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','lavfi','-i','testsrc2=size=64x64:rate=10:duration=4','-c:v','libx264',str(source)],check=True)
        videos=SimpleNamespace(root=tmp_path,db=SimpleNamespace(recording=lambda _:dict(cameraId='cam-a',duration=4)),file=lambda _:source)
        adapter=ReplayAdapter(videos);context=SimpleNamespace(deadline=time.time()+30,execution_epoch='epoch1');region=dict(x=0,y=0,width=.5,height=.5)
        window=await adapter.window('cam-a','video-a',0,2,context,region)
        frames=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries','frame=best_effort_timestamp_time','-of','json',str(window.path)]))['frames']
        assert len(frames)==20 and max(float(f['best_effort_timestamp_time']) for f in frames)<2
        with pytest.raises(ValueError):await adapter.window('cam-b','video-a',0,2,context,region)
        with pytest.raises(ValueError):await adapter.window('cam-a','video-a',0,5,context,region)
    asyncio.run(check())

def test_replay_api_confirmation_is_exclusive_and_history_stays_readable(tmp_path,monkeypatch):
    monkeypatch.setenv('EG_CAMERA_MODE','fixture')
    from fastapi.testclient import TestClient
    from evidenceguard.app import create_app
    monkeypatch.setenv('EG_VIDEO_ROOT',str(tmp_path/'media'))
    app=create_app(tmp_path/'api.sqlite',start_worker=False,provider=SimpleNamespace(name='disabled',ready=False))
    store=app.state.store;videos=app.state.videos;videos.vision.ready=True
    videos.db.save_recording(dict(id='video-a',cameraId='cam-a',duration=8,status='ready',recordedAt=None,createdAt=0))
    folder=videos.root/'video-a';folder.mkdir();(folder/'playback.mp4').write_bytes(b'0123456789')
    app.state.camera.active.manifests=AsyncMock(return_value=[])
    current=store.create_draft('已有守护',['cam-a']);store.confirm(current['id'],current['revision'])
    replay=store.create_draft('回放测试',['cam-a'],rules={'taskKind':'parcel_removal','completion':'once'});replay['replay']={'recordingId':'video-a'};store.save_skill(replay)
    from evidenceguard.skill_capabilities import fingerprint
    report=dict(id='trial-checked',skillId=replay['id'],revision=replay['revision'],fingerprint=fingerprint(replay,videos),createdAt=0,status='completed',baselineEstablished=True,failureCount=0,expectedOutcome='alert',wouldAlert=True)
    app.state.trials.save(report)
    url=f'/api/skills/{replay["id"]}/confirm'
    with TestClient(app) as client:
        assert client.post(url,json={'revision':replay['revision']}).status_code==409
        response=client.post(url,json={'revision':replay['revision'],'replayAcknowledged':True,'trialId':'trial-checked','trialReviewed':True})
        assert response.status_code==409 and response.json()['code']=='camera_occupied'
        assert store.skill(current['id'])['status']=='active'
        response=client.post(url,json={'revision':replay['revision'],'replayAcknowledged':True,'trialId':'trial-checked','trialReviewed':True,'switchFrom':{current['id']:store.skill(current['id'])['executionEpoch']}})
        assert response.status_code==200 and store.skill(current['id'])['status']=='paused'
        assert client.get('/api/recordings/video-a/video',headers={'Range':'bytes=2-4'}).content==b'234'
        item=store.skill(replay['id'])
        app.state.replay_worker.evidence(item,SimpleNamespace(recording_id='video-a',device_id='cam-a',start=0,end=7,path=folder/'playback.mp4'),5,dict(summary='测试'))
        e=store.evidence()[0]
        r=client.get(e['videoUrl'],headers={'Range':'bytes=0-3'})
        assert r.status_code==206 and r.content==b'0123'
        assert client.get('/api/replay-evidence/'+e['id']).json()['recordedAt'] is None
        assert 'videoPath' not in client.get('/api/bootstrap').json()['evidence'][0]
        ack=f'/api/skills/{replay["id"]}/replay-acknowledge'
        assert client.post(ack).status_code==409
        item.update(status='completed',alert='open');store.save_skill(item)
        assert client.post(ack).json()['alert']=='acknowledged'
        assert client.post(ack).status_code==200  # idempotent, never deletes evidence
        assert len(store.evidence())==1
        assert len([e for e in store.events(item['id']) if e['type']=='replay_acknowledged'])==1
