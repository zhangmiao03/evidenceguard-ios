import asyncio, json, time
from pathlib import Path
from unittest.mock import AsyncMock
import httpx
import pytest
from fastapi.testclient import TestClient
from evidenceguard.store import Store
from evidenceguard.video.service import VideoService, windows
from evidenceguard.video.providers import LiteVideoProvider, ArkVideoEmbedding, ProviderError, normalize
from evidenceguard.harness.tools import build_tools
from evidenceguard.app import create_app


class Embedding:
    model='embedding-test'; signature='test-signature'; ready=True
    embed=AsyncMock(return_value=[1.,0.])

class Vision:
    model='lite-test'
    def __init__(self): self.calls=[]
    async def verify(self,path,query,duration):
        self.calls.append((str(path),query,duration))
        positive='positive' in str(path)
        return dict(verdict='matched' if positive else 'not_matched',eventTime=2.5 if positive else None,
            summary='拿取动作' if positive else '只有人经过，没有拿取',events=[],limitation='')

@pytest.fixture
def env(tmp_path):
    s=Store(tmp_path/'db.sqlite'); v=VideoService(s,tmp_path/'videos',Embedding(),Vision())
    yield s,v,tmp_path
    s.close()


def recording(v,rid,camera='cam-a',at=None,positive=True,vector=None):
    folder=v.root/rid; folder.mkdir(exist_ok=True)
    (folder/'playback.mp4').write_bytes(b'0123456789')
    r=dict(id=rid,cameraId=camera,title='录像',recordedAt=at,createdAt=time.time(),sourceType='test',
        status='ready',duration=60,segmentCount=1,error=None,embeddingSignature=v.embedding.signature)
    seg=dict(id=rid+'-segment',recordingId=rid,cameraId=camera,start=15,end=35,
        path=str(folder/('positive.mp4' if positive else 'negative.mp4')),signature=v.embedding.signature)
    v.db.publish(r,[(seg,vector or [1.,0.])])
    return r,seg


def test_windows_keep_overlap_and_final_event_context():
    assert list(windows(9))==[(0,9)]
    assert list(windows(37))==[(0,20),(15,35),(30,37)]
    assert list(windows(20))==[(0,20)]


def test_retrieval_verifies_video_and_converts_clip_time_to_original(env):
    async def check():
        _,v,_=env; recording(v,'video-positive')
        result=await v.search('包裹何时被拿走','cam-a')
        assert result['videos'][0]['seekSeconds']==17.5
        assert result['videos'][0]['recordedAt'] is None
        assert result['videos'][0]['verdict']=='matched'
        assert v.vision.calls[0][2]==20
        assert result['videos'][0]['playbackUrl']=='/api/recordings/video-positive/video'
    asyncio.run(check())


def test_high_embedding_similarity_does_not_override_negative_video(env):
    async def check():
        _,v,_=env; recording(v,'video-negative',positive=False)
        hit=(await v.search('包裹被拿走'))['videos'][0]
        assert hit['similarity']==1 and hit['verdict']=='not_matched'
        assert hit['seekSeconds']==15
    asyncio.run(check())


def test_camera_scope_date_unknown_and_changed_index_model(env):
    async def check():
        s,v,_=env; recording(v,'video-a','cam-a'); recording(v,'video-b','cam-b')
        skill=s.create_draft('只看A',['cam-a'])
        result=await v.search('包裹',skill_id=skill['id'])
        assert {i['cameraId'] for i in result['videos']}=={'cam-a'}
        result=await v.search('今天包裹',period='today')
        assert not result['videos'] and result['scope']['unknownDateRecordings']==2
        v.embedding=Embedding(); v.embedding.signature='different-model-or-instructions'
        assert not (await v.search('包裹'))['videos']
    asyncio.run(check())


def test_failed_reverification_returns_uncertain_not_a_false_timestamp(env):
    async def check():
        _,v,_=env; recording(v,'video-a')
        v.vision.verify=AsyncMock(side_effect=ProviderError('视频服务不可用'))
        hit=(await v.search('包裹'))['videos'][0]
        assert hit['verdict']=='uncertain' and hit['seekSeconds']==hit['segmentStart']
        assert '不可用' in hit['limitation']
    asyncio.run(check())


def test_partial_index_is_not_searchable_and_recovers_as_interrupted(env):
    async def check():
        _,v,_=env; r,_=recording(v,'video-a')
        r['status']='indexing'; v.db.save_recording(r)
        assert not (await v.search('包裹'))['videos']
        v.recover()
        assert v.db.recording(r['id'])['status']=='interrupted'
    asyncio.run(check())


def test_history_video_tool_does_not_reach_any_camera(env):
    async def check():
        s,v,_=env; recording(v,'video-a'); camera=AsyncMock()
        tools=build_tools(s,camera,execution_mode='history',camera_id='cam-a',video_service=v)
        result=await tools.call('search_recordings',query='包裹被拿走')
        assert result['videos'] and not camera.mock_calls
        with pytest.raises(ValueError): await tools.call('request_camera_snapshot')
    asyncio.run(check())


def test_range_playback_and_path_traversal(tmp_path):
    app=create_app(tmp_path/'db.sqlite',start_worker=False,provider=type('Off',(),{'ready':False,'name':'off'})())
    with TestClient(app) as client:
        recording(app.state.videos,'video-range')
        r=client.get('/api/recordings/video-range/video',headers={'Range':'bytes=2-5'})
        assert r.status_code==206 and r.content==b'2345' and r.headers['content-range']=='bytes 2-5/10'
        assert client.get('/api/recordings/video-range/video',headers={'Range':'bytes=100-'}).status_code==416
        assert client.get('/api/recordings/not-a-recording/video').status_code==404
        assert client.get('/api/recordings/../../etc/passwd/video').status_code==404
        assert client.head('/api/recordings/video-range/video').headers['content-length']=='10'


def test_video_model_uses_video_and_retries_invalid_time_once(tmp_path,monkeypatch):
    async def check():
        monkeypatch.setenv('EG_MODEL_BASE_URL','https://model.test'); monkeypatch.setenv('EG_MODEL_ID','lite'); monkeypatch.setenv('EG_MODEL_API_KEY','test')
        movie=tmp_path/'test.mp4';movie.write_bytes(b'video')
        seen=[]
        def respond(request):
            body=json.loads(request.content); seen.append(body)
            judgment=dict(verdict='matched',summary='拿走包裹',eventTime=9 if len(seen)==1 else 3,events=[],limitation='',actionVisibility='direct')
            return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(judgment)}}]})
        original=httpx.AsyncClient
        monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(respond)))
        result=await LiteVideoProvider().verify(movie,'包裹何时被拿走',8)
        assert len(seen)==2 and result['eventTime']==3 and result['validationRetries']==1
        assert seen[0]['messages'][1]['content'][1]['type']=='video_url'
        assert seen[0]['messages'][1]['content'][1]['video_url']['url'].startswith('data:video/mp4;base64,')
    asyncio.run(check())


def test_embedding_request_is_multimodal_and_validates_dimensions(tmp_path,monkeypatch):
    async def check():
        monkeypatch.setenv('EG_MODEL_BASE_URL','https://model.test'); monkeypatch.setenv('EG_EMBED_MODEL_ID','embedding-test');monkeypatch.setenv('EG_MODEL_API_KEY','test')
        seen=[]
        def respond(request):
            seen.append(json.loads(request.content)); assert request.url.path=='/embeddings/multimodal'
            return httpx.Response(200,json={'data':{'embedding':[1.]*1024}})
        original=httpx.AsyncClient
        monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(respond)))
        movie=tmp_path/'test.mp4';movie.write_bytes(b'video')
        embed=ArkVideoEmbedding(); q=await embed.embed(text='包裹'); v=await embed.embed(video=movie)
        assert len(q)==len(v)==1024 and abs(sum(x*x for x in v)-1)<1e-6
        assert seen[0]['input'][0]['type']=='text' and seen[1]['input'][0]['type']=='video_url'
        assert seen[0]['instructions']!=seen[1]['instructions']
        with pytest.raises(ProviderError): normalize([0,0])
        with pytest.raises(ProviderError): normalize([float('nan'),1])
    asyncio.run(check())


def test_changed_embedding_marks_library_stale(env):
    _,v,_=env; r,_=recording(v,'video-stale')
    assert v.public(r)['status']=='ready'
    v.embedding=Embedding(); v.embedding.signature='new-model'
    assert v.public(r)['status']=='stale'


@pytest.mark.parametrize('verdict,visibility,event_time', [('matched','inferred',3),('not_matched','unclear',None)])
def test_occlusion_does_not_produce_a_confirmed_answer(tmp_path,monkeypatch,verdict,visibility,event_time):
    async def check():
        monkeypatch.setenv('EG_MODEL_BASE_URL','https://model.test'); monkeypatch.setenv('EG_MODEL_ID','lite'); monkeypatch.setenv('EG_MODEL_API_KEY','test')
        movie=tmp_path/'test.mp4'; movie.write_bytes(b'video')
        def respond(request):
            value=dict(verdict=verdict,summary='遮挡',eventTime=event_time,events=[],limitation='',actionVisibility=visibility)
            return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(value)}}]})
        original=httpx.AsyncClient
        monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(respond)))
        result=await LiteVideoProvider().verify(movie,'放下包裹',8)
        assert result['verdict']=='uncertain' and result['eventTime'] is None
    asyncio.run(check())


def test_selected_scope_overrides_model_date_and_reports_progress(env):
    async def check():
        _,v,_=env; recording(v,'video-a',at=1000); recording(v,'video-unknown')
        events=[]
        # Explicit all dates cannot be narrowed by a hallucinated 'today'.
        result=await v.search('包裹','cam-a',period='today',history_scope={'period':'all','startAt':None,'endAt':None},progress=lambda k,p:events.append((k,p)))
        assert len(result['videos'])==2
        assert events[0][0]=='video_search_started' and events[-1][0]=='video_search_completed'
        assert [p['completed'] for k,p in events if k=='video_verification_progress']==[1,2]
        # Explicit custom range cannot be widened by omitted model period; unknown dates excluded.
        result=await v.search('包裹','cam-a',history_scope={'period':'custom','startAt':1017,'endAt':1018})
        assert len(result['videos'])==1 and result['videos'][0]['recordingId']=='video-a'
        assert result['videos'][0]['verdict']=='matched'
        result=await v.search('包裹','cam-a',history_scope={'period':'custom','startAt':1018,'endAt':1019})
        assert result['videos'][0]['verdict']=='not_matched'
    asyncio.run(check())


def test_failure_is_not_the_same_as_occlusion(env):
    async def check():
        _,v,_=env;recording(v,'video-a')
        v.vision.verify=AsyncMock(side_effect=ProviderError('复核结果格式无效'))
        result=await v.search('包裹')
        assert result['videos'][0]['verificationStatus']=='failed'
        from evidenceguard.harness.runtime import video_answer
        assert '复核失败' in video_answer(result)
        assert '段无法确认' not in video_answer(result)
    asyncio.run(check())


def test_history_filter_validation_and_calendar_boundaries():
    from evidenceguard.history import HistoryFilter,resolve_filter
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now=datetime(2026,9,22,14,tzinfo=ZoneInfo('Asia/Shanghai')).timestamp()
    yesterday=resolve_filter({'period':'yesterday'},now)
    assert yesterday['endAt']-yesterday['startAt']==86400
    assert datetime.fromtimestamp(yesterday['endAt'],ZoneInfo('Asia/Shanghai')).hour==0
    for value in [{'period':'custom','startAt':2,'endAt':1},{'period':'custom','startAt':0,'endAt':float('inf')},{'period':'all','startAt':1}]:
        with pytest.raises(ValueError): HistoryFilter.model_validate(value)


def test_scope_is_request_identity_and_no_cards_are_invented(env):
    async def check():
        from evidenceguard.harness.runtime import AgentRuntime
        from evidenceguard.harness.tools import build_tools
        _,v,_=env;recording(v,'video-a')
        answers=iter([
            {'role':'assistant','tool_calls':[{'id':'c','type':'function','function':{'name':'search_recordings','arguments':'{"query":"包裹","period":"today"}'}}]},
            {'role':'assistant','content':'旧录像明确有被拿走，这是胡编的旧结论'}])
        provider=type('Provider',(),{'ready':True,'name':'test','complete':AsyncMock(side_effect=lambda *args:next(answers))})()
        runtime=AgentRuntime(v.store,build_tools(v.store,AsyncMock(),video_service=v),provider)
        run=runtime.start('查录像','scope-chat',request_id='scope-run',execution_mode='history',history_filter={'period':'today'})
        with pytest.raises(ValueError): runtime.start('查录像','scope-chat',request_id='scope-run',execution_mode='history',history_filter={'period':'all'})
        await asyncio.gather(*list(runtime.tasks.values()))
        result=v.store.run(run['id'])
        assert result['status']=='completed' and result['videos']==[]
        assert '胡编' not in result['text'] and '没有已完成索引的录像' in result['text']
        assert any(e['type']=='video_search_empty' for e in v.store.events(run['id']))
        await runtime.scheduler.shutdown()
    asyncio.run(check())


def test_evaluator_does_not_grade_failed_or_occluded_as_success():
    from evidenceguard.video.evaluate import assess
    assert assess({'verdict':'matched','eventTime':5},{'verdict':'uncertain'})['falseConfirmation']
    assert assess({'verdict':'matched','eventTime':7},{'verdict':'matched','eventWindow':[4.5,5.5]})['timeOutsideWindowSeconds']==1.5
    assert not assess({'verdict':'uncertain','eventTime':None},{'verdict':'matched','eventWindow':[4.5,5.5]})['structuredPass']
