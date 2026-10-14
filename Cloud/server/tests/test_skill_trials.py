import asyncio,json,time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from fastapi.testclient import TestClient
from evidenceguard.store import Store
from evidenceguard.schemas import EditSkill
from evidenceguard.skill_capabilities import assess,fingerprint
from evidenceguard.skill_trials import SkillTrials,TrialInput
from evidenceguard.app import create_app

class Vision:
    ready=True;model='test';base='test'
    async def observe_frame(self,path,query,reference=None):
        at=float(path.stem.split('-')[1])
        return dict(state='present' if at<6 else 'absent',summary='测试模型结果')

def setup(tmp_path,monkeypatch):
    store=Store(tmp_path/'db.sqlite')
    recording=dict(id='video-a',cameraId='cam-a',duration=20,recordedAt=None,sha256='digest')
    videos=SimpleNamespace(root=tmp_path,db=SimpleNamespace(recording=lambda _:recording),file=lambda _:tmp_path/'source.mp4',vision=Vision(),verify_gate=asyncio.Semaphore(2))
    (tmp_path/'source.mp4').write_bytes(b'0123456789')
    async def window(self,skill,start,end):return SimpleNamespace(device_id='cam-a',recording_id='video-a',start=start,end=end,path=tmp_path/'source.mp4')
    monkeypatch.setattr(TrialInput,'replay_window',window)
    async def sample(self,skill,at):return SimpleNamespace(path=tmp_path/f'sample-{at}.jpg')
    monkeypatch.setattr(TrialInput,'replay_sample',sample)
    s=store.create_draft('包裹被拿走提醒',['cam-a'],rules=dict(taskKind='parcel_removal',completion='once'))
    s['replay']={'recordingId':'video-a'};store.save_skill(s)
    return store,videos,SkillTrials(store,videos),s

def test_capability_never_substitutes_unsupported_or_duration_rules(tmp_path,monkeypatch):
    store,videos,trials,s=setup(tmp_path,monkeypatch)
    assert assess(s,videos)['canTrial']
    for kind in ['pet_activity','vehicle_activity','custom','unspecified']:
        s['rules']['taskKind']=kind
        assert not assess(s,videos)['canActivate']
    s['rules']['taskKind']='parcel_removal';s['rules']['durationSeconds']=30
    assert '秒数' in assess(s,videos)['blockers'][0]
    s['rules']['durationSeconds']=0;s['rules']['completion']='continuous'
    assert not assess(s,videos)['canTrial']
    store.close()

def test_trial_isolation_progress_report_and_stale_review(tmp_path,monkeypatch):
    async def check():
        store,videos,trials,s=setup(tmp_path,monkeypatch)
        live=store.create_draft('原任务',['cam-a']);store.confirm(live['id'],live['revision']);before=store.skill(live['id'])
        started=trials.start(s['id'],s['revision'],'alert');await trials.jobs[started['id']]
        report=trials.public(trials.read(started['id']))
        assert report['status']=='completed' and report['wouldAlert'] and report['canConfirm']
        assert [o['end'] for o in report['observations']]==[0,3,6,9,12]
        assert store.skill(s['id'])['status']=='draft' and store.skill(live['id'])==before
        assert not store.evidence() and store.owner('cam-a')['id']==live['id']
        with pytest.raises(ValueError):trials.require_review(s,report['id'],False)
        trials.require_review(s,report['id'],True)
        videos.vision.model='changed'
        assert trials.public(trials.read(report['id']))['stale']
        with pytest.raises(ValueError):trials.require_review(s,report['id'],True)
        videos.vision.model='test';s['revision']+=1;store.save_skill(s)
        assert not trials.public(trials.read(report['id']))['canConfirm']
        store.close()
    asyncio.run(check())

@pytest.mark.parametrize('change',['edit','cancel'])
def test_trial_cancellation_and_edit_discard_inflight_results(tmp_path,monkeypatch,change):
    async def check():
        store,videos,trials,s=setup(tmp_path,monkeypatch);entered=asyncio.Event();release=asyncio.Event()
        async def wait(*args):entered.set();await release.wait();return dict(state='present',summary='late')
        videos.vision.observe_frame=wait
        report=trials.start(s['id'],s['revision']);task=trials.jobs[report['id']];await entered.wait()
        assert trials.start(s['id'],s['revision'])['id']==report['id']
        if change=='edit':s['revision']+=1;store.save_skill(s);release.set();await task
        else:await trials.cancel(report['id'])
        r=trials.public(trials.read(report['id']))
        assert r['status']==('stale' if change=='edit' else 'cancelled') and not r['canConfirm']
        assert not store.evidence() and store.skill(s['id'])['status']=='draft'
        store.close()
    asyncio.run(check())

def test_no_baseline_and_model_failure_are_not_passes(tmp_path,monkeypatch):
    async def check():
        store,videos,trials,s=setup(tmp_path,monkeypatch)
        videos.vision.observe_frame=AsyncMock(return_value=dict(state='unknown',summary='遮挡'))
        r=trials.start(s['id'],1);await trials.jobs[r['id']]
        report=trials.public(trials.read(r['id']));assert report['status']=='completed' and not report['canConfirm'] and not report['wouldAlert']
        videos.vision.observe_frame=AsyncMock(side_effect=RuntimeError('test'))
        r=trials.start(s['id'],1);await trials.jobs[r['id']]
        report=trials.public(trials.read(r['id']));assert report['status']=='failed' and report['failureCount']==3 and not report['canConfirm']
        assert not store.evidence();store.close()
    asyncio.run(check())

def test_confirm_requires_current_review_and_rejects_other_task_report(tmp_path,monkeypatch):
    monkeypatch.setenv('EG_VIDEO_ROOT',str(tmp_path/'media'))
    app=create_app(tmp_path/'app.sqlite',start_worker=False,provider=SimpleNamespace(name='off',ready=False))
    app.state.camera.active.manifests=AsyncMock(return_value=[])
    st=app.state.store;v=app.state.videos;v.vision.ready=True
    v.db.save_recording(dict(id='video-a',cameraId='cam-a',duration=20,createdAt=0,status='ready',recordedAt=None))
    folder=v.root/'video-a';folder.mkdir();(folder/'playback.mp4').write_bytes(b'0123456789')
    s=st.create_draft('包裹拿走',['cam-a'],rules=dict(taskKind='parcel_removal',completion='once'));s['replay']={'recordingId':'video-a'};st.save_skill(s)
    with TestClient(app) as client:
        url=f'/api/skills/{s["id"]}/confirm';body=dict(revision=1,replayAcknowledged=True)
        assert client.post(url,json=body).status_code==409
        report=dict(id='trial-ready',skillId=s['id'],revision=1,createdAt=0,fingerprint=fingerprint(s,v),status='completed',baselineEstablished=True,failureCount=0,expectedOutcome='alert',wouldAlert=True)
        app.state.trials.save(report)
        assert client.post(url,json=body|dict(trialId=report['id'])).status_code==409
        response=client.post(url,json=body|dict(trialId=report['id'],trialReviewed=True))
        assert response.status_code==200
        other=st.create_draft('其他任务',['cam-a'],rules=dict(taskKind='parcel_removal',completion='once'));other['replay']=s['replay'];st.save_skill(other)
        assert client.post(f'/api/skills/{other["id"]}/confirm',json=body|dict(trialId=report['id'],trialReviewed=True)).status_code==409
        assert client.get('/api/skill-trials/trial-ready').json()['canConfirm']

def test_cancel_before_execution_and_restart_do_not_leave_running_report(tmp_path,monkeypatch):
    async def check():
        store,videos,trials,s=setup(tmp_path,monkeypatch)
        r=trials.start(s['id'],1)
        cancelled=await trials.cancel(r['id'])
        assert cancelled['status']=='cancelled'
        r=trials.start(s['id'],1)
        old=trials.read(r['id']);await trials.cancel(r['id']);old['status']='running';trials.save(old)
        recovered=SkillTrials(store,videos)
        assert recovered.read(r['id'])['status']=='interrupted'
        store.close()
    asyncio.run(check())

def test_unrecognized_execution_parameters_are_not_silently_dropped():
    from pydantic import ValidationError
    from evidenceguard.schemas import SkillRules
    with pytest.raises(ValidationError):SkillRules.model_validate({'taskKind':'parcel_removal','duration':60})

def test_draft_response_uses_capability_receipt_instead_of_model_promises(tmp_path):
    from test_harness import ScriptedProvider,tool,environment,settle
    async def check():
        provider=ScriptedProvider([tool('draft_visual_skill',dict(prompt='宠物60秒不动提醒',devices=['cam-a'],name='宠物监控',target_description='宠物',rules=dict(taskKind='pet_activity',durationSeconds=60,trigger='record_activity'))),{'role':'assistant','content':'已经启用，可直接守护宠物。'}])
        store,runtime=environment(tmp_path,provider)
        run=await settle(runtime,runtime.start('宠物60秒不动提醒','pet'))
        assert run['status']=='completed' and '还没开始运行' in run['text'] and '60 秒' in run['text']
        assert '可直接守护' not in run['text'] and not run['draft']['capability']['canActivate']
        assert store.skill(run['draft']['id'])['rules']['durationSeconds']==60
        store.close()
    asyncio.run(check())
