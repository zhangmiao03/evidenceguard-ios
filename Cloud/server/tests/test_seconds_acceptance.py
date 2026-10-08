import asyncio,json,time,subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import httpx,pytest
from evidenceguard.schemas import SkillRules
from evidenceguard.timing import accumulate
from evidenceguard.deployment import SitePreparation
from evidenceguard.store import Store
from evidenceguard.camera.adapters.replay import ReplayAdapter
from evidenceguard.video.providers import LiteVideoProvider

@pytest.mark.parametrize('value',[0,1,2,2.9])
def test_sampling_cannot_be_less_than_three_seconds(value):
    with pytest.raises(ValueError):SkillRules(sampleIntervalSeconds=value)

def test_span_must_cover_at_least_one_interval():
    with pytest.raises(ValueError):SkillRules(sampleIntervalSeconds=10,confirmationSeconds=6)
    rules=SkillRules.model_validate({'consecutiveFrames':3})
    assert rules.sampleIntervalSeconds==3 and rules.confirmationSeconds==6
    assert 'consecutiveFrames' not in rules.model_dump()

def test_confirmation_uses_elapsed_sample_time_not_count():
    c={}
    for at in [0,.1,.2,1,2]:c=accumulate(c,'absent',at,str(at),3)
    assert c['span']==0
    c=accumulate(c,'absent',3,'3',3);assert c['span']==3
    assert accumulate(c,'absent',6,'3',3)==c  # repeated proof
    c=accumulate(c,'absent',6,'6',3);assert c['span']==6
    assert accumulate(c,'absent',15,'15',3)['span']==0  # missed sampling breaks continuity
    assert accumulate(c,'present',9,'9',3)['span']==0

def test_site_checklist_is_revision_scoped_and_never_grants_publish(tmp_path):
    store=Store(tmp_path/'db');s=store.create_draft('包裹离区',['cam-a','cam-b'],rules={'taskKind':'parcel_removal'})
    prep=SitePreparation(store);plan=prep.read(s)
    assert [c['position'] for c in plan['cameras']]==['eaves','doorbell']
    for action in plan['actions']:plan=prep.update(s,s['revision'],action['id'],True)
    assert all(a['completed'] for a in plan['actions']) and not plan['canPublish']
    s['revision']+=1;store.save_skill(s)
    assert not any(a['completed'] for a in prep.read(s)['actions'])
    with pytest.raises(ValueError):prep.update(s,s['revision']-1,'positive',True)
    store.close()

def test_old_active_rule_pauses_for_seconds_review(tmp_path):
    path=tmp_path/'db';store=Store(path)
    s=store.create_draft('旧任务',['cam-a']);s=store.confirm(s['id'],1)
    s['rules'].pop('sampleIntervalSeconds');s['rules'].pop('confirmationSeconds');s['rules']['consecutiveFrames']=3
    store.save_skill(s);store.close()
    store=Store(path);s=store.skill(s['id'])
    assert s['status']=='paused' and s['needsTimingReview'] and s['revision']==2
    with pytest.raises(ValueError):store.lifecycle(s['id'],'resume')
    store.close()

def test_sample_adapter_outputs_one_jpeg_and_never_a_future_frame(tmp_path):
    async def check():
        source=tmp_path/'source.mp4'
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','lavfi','-i','testsrc2=size=128x128:rate=10:duration=4','-c:v','libx264',str(source)],check=True)
        videos=SimpleNamespace(root=tmp_path,db=SimpleNamespace(recording=lambda _:dict(cameraId='cam-a',duration=4)),file=lambda _:source)
        adapter=ReplayAdapter(videos);context=SimpleNamespace(deadline=time.time()+30,execution_epoch='epoch')
        for at in [0,3.05]:
            result=await adapter.sample('cam-a','video-a',at,context,dict(x=0,y=0,width=.1,height=.1))
            image=subprocess.check_output(['ffmpeg','-v','error','-i',str(result.path),'-f','rawvideo','-pix_fmt','rgb24','pipe:1'])
            expected=subprocess.check_output(['ffmpeg','-v','error','-i',str(source),'-vf',f'select=eq(n\\,{int(at*10)})','-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'])
            assert len(image)==128*128*3 and len(expected)==len(image)
            # JPEG and source differ slightly in compression; ignore drawn ROI.
            image=image[30*128*3:];expected=expected[30*128*3:]
            assert sum(abs(a-b) for a,b in zip(image,expected))/len(image)<6
        with pytest.raises(ValueError):await adapter.sample('cam-b','video-a',0,context,{})
    asyncio.run(check())

def test_guard_provider_sends_stills_and_rejects_occluded_absence(tmp_path,monkeypatch):
    async def check():
        monkeypatch.setenv('EG_MODEL_BASE_URL','https://model.test');monkeypatch.setenv('EG_MODEL_ID','lite');monkeypatch.setenv('EG_MODEL_API_KEY','test')
        path=tmp_path/'frame.jpg';path.write_bytes(b'jpeg');original=httpx.AsyncClient
        def reply(request):
            body=json.loads(request.content);content=body['messages'][1]['content']
            assert len([v for v in content if v['type']=='image_url'])==2
            assert not any(v['type']=='video_url' for v in content)
            return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(dict(state='absent',regionClear=False,identityClear=False,summary='遮挡'))}}]})
        monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(reply)))
        result=await LiteVideoProvider().observe_frame(path,'包裹',path)
        assert result['state']=='unknown'
    asyncio.run(check())

def test_short_positive_video_and_unlabelled_exploration_are_not_accepted(tmp_path,monkeypatch):
    from test_skill_trials import setup
    async def check():
        store,videos,trials,s=setup(tmp_path,monkeypatch)
        r=trials.start(s['id'],1,'explore');await trials.jobs[r['id']]
        assert trials.read(r['id'])['wouldAlert'] and not trials.public(trials.read(r['id']))['canConfirm']
        videos.db.recording=lambda _:dict(id='video-a',cameraId='cam-a',duration=8,sha256='digest')
        r=trials.start(s['id'],1,'alert');await trials.jobs[r['id']]
        r=trials.public(trials.read(r['id']))
        assert [o['start'] for o in r['observations']]==[0,3,6]
        assert not r['wouldAlert'] and not r['canConfirm']
        store.close()
    asyncio.run(check())

def test_negative_acceptance_requires_clear_coverage(tmp_path,monkeypatch):
    from test_skill_trials import setup
    async def check():
        store,videos,trials,s=setup(tmp_path,monkeypatch)
        videos.vision.observe_frame=AsyncMock(return_value=dict(state='present',summary='在场'))
        r=trials.start(s['id'],1,'no_alert');await trials.jobs[r['id']]
        assert trials.public(trials.read(r['id']))['canConfirm']
        videos.vision.observe_frame=AsyncMock(side_effect=[dict(state='present',summary='在场')]+[dict(state='unknown',summary='遮挡')]*6)
        r=trials.start(s['id'],1,'no_alert');await trials.jobs[r['id']]
        assert not trials.public(trials.read(r['id']))['canConfirm']
        store.close()
    asyncio.run(check())

def test_sdk_publish_cannot_be_unlocked_by_user_preparation(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from evidenceguard.app import create_app
    monkeypatch.setenv('EG_VIDEO_ROOT',str(tmp_path/'videos'))
    app=create_app(tmp_path/'db',start_worker=False,provider=SimpleNamespace(name='off',ready=False))
    app.state.camera.active.manifests=AsyncMock(return_value=[])
    s=app.state.store.create_draft('包裹离区',['cam-a','cam-b'],rules={'taskKind':'parcel_removal'})
    with TestClient(app) as client:
        url=f'/api/skills/{s["id"]}/deployment'
        plan=client.get(url).json()
        for a in plan['actions']:
            assert client.post(url+'/preparation',json=dict(revision=1,action=a['id'],completed=True)).status_code==200
        assert client.get(url).json()['canPublish']==False
        assert client.post(f'/api/skills/{s["id"]}/publish').status_code==409
