"""Explicit public replay through the deployed guard harness and real VLM.

This is NOT a live-camera test. It uses an isolated business store, never calls
the capture/control services, and preserves stored_video_replay provenance.
Only the opt-in observability database and bounded input cache receive records.
Run with the deployed demo venv through authorized server maintenance access.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace


async def verify(config, recording_id, expected_sha, offsets):
    assert re.fullmatch(r'video-[a-f0-9]{16}', recording_id)
    assert re.fullmatch(r'[a-f0-9]{64}', expected_sha)
    settings=json.loads(Path(config).read_text())
    environment=settings['environments']['demo']
    state=json.loads(Path(environment['state']).read_text())
    pid=subprocess.check_output(['systemctl','show',environment['service'],'-p','MainPID','--value'],text=True).strip()
    assert str(state['pid'])==pid, 'Running process and observer state differ'
    assert state.get('guardTracking')=='per_run_v1', 'Deploy guard diagnostics first'
    env=dict(v.split('=',1) for v in Path('/proc',pid,'environ').read_bytes().decode().split('\0') if '=' in v)
    from dotenv import dotenv_values
    env={**dotenv_values(env.get('EG_ENV_FILE','/etc/evidenceguard-demo/cloud.env')),**env}
    assert env.get('EG_DASHBOARD_CAPTURE_CONTENT')=='1' and env.get('EG_DASHBOARD_CAPTURE_MEDIA')=='1'
    os.environ.update({k:v for k,v in env.items() if isinstance(v,str)})
    sys.path.insert(0,str(Path(environment['source']).parent))
    from evidenceguard import ops
    from evidenceguard.store import Store
    from evidenceguard.video.providers import LiteVideoProvider
    from evidenceguard.visual_review import VisualReview
    from evidenceguard.visual_skills.harness import SceneHarness
    from evidenceguard.visual_skills.audit import GuardRun, event, frame_reference
    from evidenceguard.vision.processing import LocalVision
    from eg_dashboard import transport,content
    transport.install(ops)
    with sqlite3.connect(Path(environment['database']).as_uri()+'?mode=ro',uri=True) as database:
        row=database.execute('SELECT payload FROM recordings WHERE id=?',(recording_id,)).fetchone()
        assert row, 'Published recording no longer exists'
        recording=json.loads(row[0])
    root=Path(state['videoRoot']).resolve()
    video=root/recording_id/'playback.mp4'
    assert not video.is_symlink() and not video.parent.is_symlink() and video.resolve().is_relative_to(root)
    assert hashlib.sha256(video.read_bytes()).hexdigest()==expected_sha, 'Recording bytes changed'
    manifest=json.loads((Path(settings['output'])/'media/demo/manifest.json').read_text())
    assert expected_sha in manifest['items'], 'Only an already published video can be used'
    assert 0<=offsets[0]<offsets[1]<recording['duration']
    local=LocalVision()
    assert local.guard_enabled and local.configuration()['depthReady'], 'Use actual ready deployed configuration'
    recorder=ops.Recorder(environment['observations'],capture=False)
    try:
        with tempfile.TemporaryDirectory(prefix='eg-guard-public-replay-') as folder:
            store=Store(Path(folder)/'isolated.sqlite3')
            store.ops=recorder
            try:
                samples=[]
                began=time.monotonic()
                for i,offset in enumerate(offsets):
                    raw=subprocess.check_output(['ffmpeg','-v','error','-ss',str(offset),'-i',str(video),
                        '-frames:v','1','-vf','scale=640:-2','-f','image2pipe','-vcodec','mjpeg','-threads','1','-'],timeout=20)
                    meta=dict(device_id=recording['cameraId'],channel_id='saved-video',session_id='public-replay',
                        view_revision='saved-video:0',frame_id=f'replay-{offset}',source_type='stored_video_replay',
                        freshness='stored_recording',sampled_at=offset,decoder_frame=False)
                    media=store.save_media(meta,raw,'image/jpeg')
                    samples.append(dict(id=f'replay-capture-{i}',status='completed',mediaId=media['id'],
                        sourceType='stored_video_replay',frameId=meta['frame_id'],sampledAt=offset,
                        timestampMeaning='offset_in_saved_recording',viewRevision='saved-video:0'))
                scene=dict(id='public-replay-'+recording_id,revision=1,cameraId=recording['cameraId'],
                    frame=samples[0],box=dict(x=0.05,y=0.05,width=.9,height=.9),
                    plan=dict(title='已保存视频 · 水瓶区域验证',target='水瓶',selection='region',trigger='leaves',
                              confirmationSeconds=15,completion='continuous'))
                harness=SceneHarness(SimpleNamespace(ready=True),VisualReview(store,LiteVideoProvider()))
                harness.local_vision=local
                assert harness.vision_port().ready, 'Use the configured real guard vision provider'
                with GuardRun(store,scene,mode='stored_video_replay') as run:
                    event('capture',frame=frame_reference(samples[1]),duration=round((time.monotonic()-began)*1000,2),
                          recordingId=recording_id,recordingSha256=expected_sha,sampleOffsets=offsets)
                    judgment=await harness.observe(scene,samples[1],store)
                    run.finish(disposition='replay_only',judgment=judgment,alertPublished=False,
                               hardwareCalled=False,businessStore='isolated_temporary')
                assert recorder.flush(timeout=8), 'Telemetry queue did not persist in time'
                with recorder.lock:
                    records=[json.loads(r[0]) for r in recorder.db.execute(
                        'SELECT payload FROM critical_records WHERE trace_id=? ORDER BY at,rowid',(run.id,))]
                pre=[r for r in records if r['name']=='guard.preprocessing' and r['status']!='started'][-1]
                models=[r for r in records if r['kind']=='model']
                prompts=[r for r in records if r['kind']=='prompt']
                assert pre['data']['depth']['status']=='completed'
                assert pre['data']['flow']=={'status':'skipped','code':'LIVE_SAMPLE_REQUIRED'}
                assert len(models)==len(prompts)==1 and models[0]['status']=='http_ok'
                inputs=prompts[0]['data']['inputMedia']
                assert len(inputs)==6 and all(i['status']=='captured' for i in inputs)
                for item in inputs:
                    suffix='.jpg' if item['mime']=='image/jpeg' else '.png'
                    path=Path(recorder.path).parent/'observer-media'/(item['assetId']+suffix)
                    assert hashlib.sha256(path.read_bytes()).hexdigest()==item['assetId']
                encoded=json.dumps(records,ensure_ascii=False)
                assert not any(secret in encoded for secret in content.secret_values()), 'Secret filter check failed'
                assert recorder.dropped==recorder.write_errors==0
                return dict(validation='passed',mode='stored_video_replay',traceId=run.id,
                    recordingId=recording_id,recordingSha256=expected_sha,sampleOffsets=offsets,
                    depth=pre['data']['depth'],flow=pre['data']['flow'],preprocessingMs=pre['durationMs'],
                    model=models[0]['data']['model'],modelDurationMs=models[0]['durationMs'],
                    records=len(records),inputCopies=len(inputs),judgment=judgment,
                    telemetryDropped=recorder.dropped,telemetryWriteErrors=recorder.write_errors,
                    liveCameraValidated=False,hardwareCalls=0,businessStore='isolated_temporary')
            finally:
                store.close()
    finally:
        await local.close()
        recorder.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',default='/etc/evidenceguard-dashboard/config.json')
    parser.add_argument('--recording',required=True)
    parser.add_argument('--sha256',required=True)
    parser.add_argument('--first',type=float,default=44.0)
    parser.add_argument('--second',type=float,default=44.5)
    args=parser.parse_args()
    print(json.dumps(asyncio.run(verify(args.config,args.recording,args.sha256,[args.first,args.second])),ensure_ascii=False))
