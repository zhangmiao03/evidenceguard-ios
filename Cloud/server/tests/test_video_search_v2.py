import asyncio, base64, io, json, math, shutil, time
from pathlib import Path
from unittest.mock import AsyncMock
import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from evidenceguard.app import create_app
from evidenceguard.store import Store
from evidenceguard.video.service import VideoService, command
from evidenceguard.video.index_v2 import RetrievalIndex, vector_blob, fuse, top, DIMENSIONS
from evidenceguard.video.index_media import representatives
from evidenceguard.video.providers import ArkVideoEmbedding, LiteVideoProvider, ProviderError
from evidenceguard.video.search import SearchInput
from evidenceguard.history import resolve_filter
from evidenceguard.harness.tools import build_tools


def vec(index=0):
    result=[0.]*DIMENSIONS; result[index]=1.; return result


def jpeg():
    stream=io.BytesIO(); Image.new('RGB',(64,48),'blue').save(stream,format='JPEG'); return stream.getvalue()


class EmbeddingV2:
    ready=True; model='test-model'; signature='legacy'; corpus_signature='v2-test'; query_signature='q2-test'
    def __init__(self): self.calls=[]; self.fail_at=None
    async def embed_v2(self,**kwargs):
        self.calls.append(kwargs)
        if len(self.calls)==self.fail_at: raise ProviderError('controlled failure')
        return vec()


class VisionV2:
    model='vision-test'
    def __init__(self): self.calls=[]; self.release=None; self.fail=False; self.offset=1.
    async def verify(self,path,query,duration,**kwargs):
        self.calls.append((path,query,duration,kwargs))
        if self.release: await self.release.wait()
        if self.fail: raise RuntimeError('transport failure')
        return dict(verdict='matched',summary='看见参考目标',eventTime=self.offset,events=[],limitation='仅比较外观',actionVisibility='direct')


@pytest.fixture
def service(tmp_path,monkeypatch):
    monkeypatch.setenv('EG_CAMERA_SOURCE','fixture_lab')
    monkeypatch.delenv('EG_VIDEO_INDEX_V2',raising=False)
    store=Store(tmp_path/'db.sqlite'); value=VideoService(store,tmp_path/'videos',EmbeddingV2(),VisionV2())
    yield value
    store.close()


def indexed(service,rid='video-one',camera='cam-a',at=None,start=0,end=20,signature=None,publish=True,vector=None,source='uploaded',total=60):
    signature=signature or service.index_signature
    folder=service.root/rid; folder.mkdir(exist_ok=True)
    (folder/'playback.mp4').write_bytes(b'0123456789')
    (folder/'clip.mp4').write_bytes(b'clip')
    image=folder/'frame.jpg'; image.write_bytes(jpeg())
    try: r=service.db.recording(rid)
    except KeyError:
        r=dict(id=rid,cameraId=camera,recordedAt=at,sourceType=source,title='录像',status='ready',duration=total,
            createdAt=time.time(),segmentCount=1,error=None,embeddingSignature=signature)
    service.db.save_recording(r); service.index_db.begin(r,signature)
    clip=dict(id=rid+'-'+str(start),recordingId=rid,cameraId=camera,continuityId=rid,start=start,end=end,path=str(folder/'clip.mp4'))
    embeddings=[]
    for kind,offset in [('video',-1),('frame',round((start+1)*1000))]:
        key=clip['id']+signature+kind
        service.index_db.save_unit(key,signature,'test-model',vector or vec())
        embeddings.append((kind,offset,key,str(image) if kind=='frame' else None))
    service.index_db.save_clip(clip,signature,embeddings)
    if publish:
        with service.store.lock:
            n=service.store.db.execute('SELECT count(*) FROM retrieval_clips WHERE recording_id=? AND signature=?',(rid,signature)).fetchone()[0]
        service.index_db.publish(r,signature,n)
    return r,clip


async def finish(service,request,owner='alice'):
    response=service.retrieval.start(SearchInput(**request),owner)
    await service.retrieval.jobs[response['id']]
    return service.retrieval.get(response['id'],owner)


@pytest.mark.parametrize('bad',[[0.]*1024,[1.]*1023,[math.nan]*1024,[math.inf]*1024,[True]*1024,['1']*1024])
def test_blob_rejects_invalid_vectors(bad):
    with pytest.raises(ValueError): vector_blob(bad)


def test_float32_binary_normalization_and_partial_top_k():
    blob=vector_blob([2.]*1024)
    assert len(blob)==4096 and np.linalg.norm(np.frombuffer(blob,dtype='<f4'))==pytest.approx(1)
    values={f'{i:04}':(float(i%37),None) for i in range(1300)}
    expected=sorted(((k,*v) for k,v in values.items()),key=lambda x:(-x[1],x[0]))[:20]
    assert top(values)==expected


def test_scope_versions_and_unknown_dates_filter_before_vector_read(service):
    indexed(service,at=1000); indexed(service,'video-other','cam-b',at=1000)
    indexed(service,'video-unknown','cam-a',at=None)
    indexed(service,'video-legacy','cam-a',at=1000,signature='old')
    hits,metrics=service.index_db.recall(vec(),service.index_signature,cameras={'cam-a'},start=1000,end=1010)
    assert [hit['clip']['recordingId'] for hit in hits]==['video-one']
    assert metrics['vectorCount']==2
    assert service.index_db.recall(vec(),'missing')[0]==[]


def test_atomic_publication_keeps_previous_generation_and_resumable_units(service):
    r,clip=indexed(service)
    generation=service.index_db.generation
    indexed(service,signature='next',publish=False)
    assert service.index_db.generation==generation
    assert len(service.index_db.recall(vec(),'v2-test')[0])==1
    assert service.index_db.recall(vec(),'next')[0]==[]
    service.index_db.failed(r['id'],'next','failed','network')
    service.index_db.begin(r,'next')
    assert service.index_db.has_unit(clip['id']+'nextvideo')
    service.index_db.publish(r,'next',1)
    assert service.index_db.recall(vec(),'v2-test')[0]==[]
    assert len(service.index_db.recall(vec(),'next')[0])==1
    assert service.index_db.generation==generation+1


def test_missing_frame_prevents_publication(service):
    r,clip=indexed(service,publish=False)
    with service.store.transaction(): service.store.db.execute("DELETE FROM retrieval_embeddings WHERE kind='frame'")
    with pytest.raises(ValueError): service.index_db.publish(r,service.index_signature,1)
    assert not service.index_db.recall(vec(),service.index_signature)[0]


def test_rrf_frame_aggregation_and_time_nms_keep_distant_events():
    clips={str(i):dict(cameraId='cam-a',continuityId='same',start=a,end=a+20) for i,a in enumerate([0,2,45])}
    result=fuse({'0':(.9,None),'1':(.8,None),'2':(.7,None)},
        {'2':(.99,{'offset':46}),'0':(.8,{'offset':1}),'1':(.7,{'offset':3})},clips,10)
    assert len(result)==2
    assert any(v['clip']['start']==45 for v in result)
    assert any(len(v['intervals'])==2 for v in result)


def test_matrix_chunked_recall_matches_numpy_reference(service):
    _,clip=indexed(service)
    rng=np.random.default_rng(6)
    vectors=rng.normal(size=(1100,1024)).astype(np.float32)
    vectors/=np.linalg.norm(vectors,axis=1)[:,None]
    # >1024 frame rows forces two independent vector blocks.
    with service.store.transaction():
        for i,vector in enumerate(vectors):
            key=f'random-{i}'
            service.index_db.save_unit(key,service.index_signature,'test-model',vector)
            service.store.db.execute('INSERT INTO retrieval_embeddings VALUES (?,?,?,?,?,?)',
                (clip['id'],service.index_signature,'frame',i+2000,key,None))
    q=rng.normal(size=1024); q=q/np.linalg.norm(q)
    hits,metrics=service.index_db.recall(q,service.index_signature)
    expected=max(float(np.max(vectors@q)),float(q[0]))
    assert hits[0]['ranks']['frame']['cosine']==pytest.approx(expected,abs=1e-6)
    assert metrics['vectorCount']==1102


def test_candidates_published_before_verification_and_reference_preserved(service):
    async def check():
        indexed(service)
        image=service.retrieval.upload_image('alice',jpeg())
        service.vision.release=asyncio.Event()
        value=service.retrieval.start(SearchInput(text='有人放下这个物体',image_ref=image['id']),'alice')
        task=service.retrieval.jobs[value['id']]
        for _ in range(200):
            current=service.retrieval.get(value['id'],'alice')
            if current['videos']: break
            await asyncio.sleep(.005)
        assert current['status']=='verifying' and current['videos'][0]['verdict']=='candidate' and not task.done()
        service.vision.release.set(); await task
        result=service.retrieval.get(value['id'],'alice')
        assert result['videos'][0]['verdict']=='matched'
        assert service.embedding.calls==[dict(text='有人放下这个物体',image=service.retrieval.image_path(image['id'],'alice'))]
        assert service.vision.calls[0][1]=='有人放下这个物体'
        assert service.vision.calls[0][3]['reference_image'].read_bytes()==service.retrieval.image(image['id'],'alice')
    asyncio.run(check())


def test_failed_verification_is_distinct_and_date_boundary_not_a_match(service):
    async def check():
        indexed(service,at=1000)
        service.vision.fail=True
        result=await finish(service,dict(text='包裹'))
        assert result['status']=='completed'
        assert result['videos'][0]['verdict']=='verification_failed'
        service.vision.fail=False
        result=await finish(service,dict(text='包裹',time_range=dict(period='custom',startAt=1005,endAt=1010)))
        assert result['videos'][0]['verdict']=='not_matched'
        assert result['videos'][0]['seekSeconds']>=5
        with pytest.raises(KeyError): service.retrieval.thumbnail(result['id'],result['videos'][0]['id'],'alice')
    asyncio.run(check())


def test_no_recordings_unindexed_and_image_owner_isolation(service):
    async def check():
        assert (await finish(service,dict(text='箱子')))['status']=='no_recordings'
        indexed(service,publish=False)
        assert (await finish(service,dict(text='箱子')))['status']=='no_indexed_recordings'
        image=service.retrieval.upload_image('alice',jpeg())
        with pytest.raises(KeyError): service.retrieval.start(SearchInput(image_ref=image['id']),'bob')
        result=await finish(service,dict(text='箱子'))
        with pytest.raises(KeyError): service.retrieval.get(result['id'],'bob')
    asyncio.run(check())


def test_delete_removes_vectors_media_and_old_search_cards(service):
    async def check():
        indexed(service)
        result=await finish(service,dict(text='箱子'))
        await service.delete_recording('video-one')
        assert not (service.root/'video-one').exists()
        assert not service.index_db.recall(vec(),service.index_signature)[0]
        current=service.retrieval.get(result['id'],'alice')
        assert not current['videos'] and current['removedCandidates']==1 and current['indexChanged']
        with pytest.raises(KeyError): service.file('video-one')
    asyncio.run(check())


def test_same_upload_is_idempotent_and_date_change_is_a_new_source(service,tmp_path):
    file=tmp_path/'source';file.write_bytes(b'actual-file')
    first=service.stage(file,'cam-a',title='one')
    assert service.stage(file,'cam-a',title='two')['id']==first['id']
    assert service.stage(file,'cam-a',100)['id']!=first['id']
    assert service.stage(file,'cam-b')['id']!=first['id']


def test_midnight_timezone_unknown_and_empty_queries():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now=datetime(2026,10,16,0,15,tzinfo=ZoneInfo('America/New_York')).timestamp()
    result=resolve_filter({'period':'yesterday'},now,timezone='America/New_York')
    assert datetime.fromtimestamp(result['endAt'],ZoneInfo('America/New_York')).hour==0
    assert result['endAt']-result['startAt']==86400
    for value in ({},{'text':'   '},{'text':'box','timezone':'bogus'},{'text':'box','tenant_id':'other'}):
        with pytest.raises(ValueError): SearchInput(**value)


def test_three_independent_representatives_not_a_joint_corpus():
    selected=representatives([dict(offset=i,sharpness=i%4,file=str(i)) for i in range(20)],0,20)
    assert len(selected)==3 and selected[0]['offset']<20/3<=selected[1]['offset']<40/3<=selected[2]['offset']


def test_http_image_search_scope_requires_private_key(tmp_path,monkeypatch):
    monkeypatch.setenv('EG_CAMERA_SOURCE','fixture_lab')
    monkeypatch.setenv('EG_VIDEO_ROOT',str(tmp_path/'videos'))
    app=create_app(tmp_path/'http.sqlite',start_worker=False,provider=type('Off',(),{'ready':False,'name':'off'})())
    with TestClient(app) as client:
        app.state.videos.embedding=EmbeddingV2();app.state.videos.vision=VisionV2()
        indexed(app.state.videos)
        owner={'X-EG-Installation-ID':'11111111-1111-4111-8111-111111111111','X-EG-Private-Key':'a'*48}
        other={'X-EG-Installation-ID':'22222222-2222-4222-8222-222222222222','X-EG-Private-Key':'b'*48}
        assert client.post('/api/video-search',json={'text':'box'},headers={'X-EG-Installation-ID':'33333333-3333-4333-8333-333333333333'}).status_code==403
        image=client.post('/api/video-search-images',content=jpeg(),headers=owner).json()
        assert client.get(image['url'],headers=owner).status_code==200
        assert client.get(image['url'],headers=other).status_code==404
        assert client.get(image['url'],headers={'X-EG-Installation-ID':'11111111-1111-4111-8111-111111111111','X-EG-Private-Key':'b'*48}).status_code==403
        assert client.post('/api/video-search',json={'image_ref':image['id']},headers=other).status_code==404
        response=client.post('/api/video-search',json={'text':'box','image_ref':image['id']},headers=owner)
        assert response.status_code==202
        key=response.json()['id']
        assert client.get('/api/video-search/'+key,headers=other).status_code==404
        assert client.get('/api/recordings/video-one/video',headers={'Range':'bytes=2-5'}).status_code==206


def test_official_source_filter_applies_to_all_media_routes(tmp_path,monkeypatch):
    monkeypatch.setenv('EG_CAMERA_SOURCE','official_sdk')
    monkeypatch.setenv('EG_VIDEO_ROOT',str(tmp_path/'videos'))
    app=create_app(tmp_path/'http.sqlite',start_worker=False,provider=type('Off',(),{'ready':False,'name':'off'})())
    with TestClient(app) as client:
        app.state.videos.embedding=EmbeddingV2();app.state.videos.vision=VisionV2()
        indexed(app.state.videos,source='public_sample')
        for suffix in ('','/video','/preview'):
            assert client.get('/api/recordings/video-one'+suffix).status_code==404
        assert client.post('/api/recordings/video-one/index').status_code==404


def test_latest_ios_guard_contract_preserves_private_history_retrieval(tmp_path,monkeypatch):
    from test_harness import ScriptedProvider, tool, settle
    monkeypatch.setenv('EG_CAMERA_SOURCE','fixture_lab')
    monkeypatch.setenv('EG_VIDEO_ROOT',str(tmp_path/'videos'))
    monkeypatch.setenv('EG_AGENT_EXECUTOR','bounded-chat-v1')
    monkeypatch.delenv('EG_VIDEO_INDEX_V2',raising=False)
    provider=ScriptedProvider([tool('search_recordings',{'query':'模型缩短后的描述'}),
        {'role':'assistant','content':'请查看这段录像。'},
        tool('search_recordings',{'query':'蓝色物体'}), {'role':'assistant','content':'找到一段录像。'},
        {'role':'assistant','content':'你好。'}])
    app=create_app(tmp_path/'integration.sqlite',start_worker=False,provider=provider)
    owner={'X-EG-Installation-ID':'11111111-1111-4111-8111-111111111111','X-EG-Private-Key':'a'*48}
    other={'X-EG-Installation-ID':'22222222-2222-4222-8222-222222222222','X-EG-Private-Key':'b'*48}
    with TestClient(app) as client:
        videos=app.state.videos
        videos.embedding=EmbeddingV2(); videos.vision=VisionV2()
        indexed(videos)
        image=client.post('/api/video-search-images',content=jpeg(),headers=owner).json()
        body=dict(message='有人将参考图中的物体放到门边',conversationId='history-integration',
            requestId='history-image-001',executionMode='history',historyFilter={'period':'all'},
            clientPlatform='ios',guardFlowVersion=1,referenceImageId=image['id'])
        response=client.post('/api/agent/runs',json=body,headers=owner)
        assert response.status_code==202
        value=client.portal.call(settle,app.state.agent,response.json())
        assert value['status']=='completed' and value['referenceImageId']==image['id']
        assert value['guardFlowVersion'] is None
        names=set(value['executionContract']['allowed_tools'])
        assert 'search_recordings' in names
        assert not names & {'create_camera_guard','revise_camera_guard','draft_visual_skill',
            'request_camera_snapshot','request_recheck','save_personal_task'}
        assert value['videos'][0]['verdict']=='matched' and value['videos'][0]['referenceImageUsed']
        assert videos.embedding.calls[0]['text']==body['message']
        assert videos.vision.calls[0][1]==body['message']
        assert videos.vision.calls[0][3]['reference_image']==videos.embedding.calls[0]['image']
        assert app.state.visual_scenes.list_all()==[] and app.state.store.skills()==[]
        # Retrying keeps the same query; the new guard flag cannot discard image identity.
        assert client.post('/api/agent/runs',json=body,headers=owner).json()['id']==value['id']
        assert len(videos.embedding.calls)==1
        assert client.post('/api/agent/runs',json=body|{'referenceImageId':None},headers=owner).status_code==409
        assert client.post('/api/agent/runs',json=body|{'conversationId':'foreign-history','requestId':'foreign-001'},headers=other).status_code==404
        assert client.post('/api/agent/runs',json=body|{'executionMode':'live'},headers=owner).status_code==409
        # Text-only Agent searches must also belong to this installation, so the
        # same HTTP status API can resume them without a shared team-tool owner.
        response=client.post('/api/agent/runs',headers=owner,json=body|{
            'message':'蓝色物体','requestId':'history-text-002','referenceImageId':None})
        assert response.status_code==202
        plain=client.portal.call(settle,app.state.agent,response.json())
        assert plain['status']=='completed'
        path='/api/video-search/'+plain['videoSearch']['id']
        assert client.get(path,headers=owner).status_code==200
        assert client.get(path,headers=other).status_code==404
        # The same new iOS client still gains the intended guard tools in a live turn.
        response=client.post('/api/agent/runs',headers=owner,json=dict(message='你好',
            conversationId='live-integration',requestId='live-guard-001',clientPlatform='ios',guardFlowVersion=1))
        assert response.status_code==202
        live=client.portal.call(settle,app.state.agent,response.json())
        assert live['status']=='completed' and live['guardFlowVersion']==1
        assert live['referenceImageId'] is None
        assert 'create_camera_guard' in live['executionContract']['allowed_tools']
        assert 'draft_visual_skill' not in live['executionContract']['allowed_tools']


def test_provider_joint_request_and_reference_video_verification(monkeypatch,tmp_path):
    requests=[]
    def handle(request):
        body=json.loads(request.content); requests.append(body)
        if str(request.url).endswith('/embeddings/multimodal'): return httpx.Response(200,json={'data':{'embedding':vec()}})
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(dict(verdict='matched',summary='外观相似',eventTime=1,events=[],actionVisibility='direct'))}}]})
    real=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(handle),**kw))
    for name in ('EG_EMBED_BASE_URL','EG_VIDEO_BASE_URL'): monkeypatch.setenv(name,'https://model.test')
    for name in ('EG_EMBED_API_KEY','EG_VIDEO_API_KEY'): monkeypatch.setenv(name,'test')
    monkeypatch.setenv('EG_EMBED_MODEL_ID','model');monkeypatch.setenv('EG_VIDEO_MODEL_ID','vision')
    image=tmp_path/'image.jpg';image.write_bytes(jpeg())
    video=tmp_path/'clip.mp4';video.write_bytes(b'video')
    async def check():
        provider=ArkVideoEmbedding()
        await provider.embed_v2(text='放下这个包',image=image)
        await provider.embed_v2(image=image,corpus=True)
        await provider.embed_v2(video=video,corpus=True)
        await LiteVideoProvider().verify(video,'放下这个包',10,reference_image=image)
        assert provider.signature!=provider.corpus_signature and provider.query_signature!=provider.corpus_signature
    asyncio.run(check())
    assert [v['type'] for v in requests[0]['input']]==['image_url','text']
    assert requests[0]['instructions'].startswith('Target_modality: image/video.') and requests[0]['dimensions']==1024
    assert requests[1]['instructions']=='Instruction:Compress the image into one word.\nQuery:'
    assert requests[2]['input'][0]['video_url']['fps']==1
    content=requests[3]['messages'][1]['content']
    assert [v['type'] for v in content]==['text','image_url','video_url']
    assert '放下这个包' in content[0]['text']


@pytest.mark.skipif(not shutil.which('ffmpeg'),reason='ffmpeg is required for the real media preprocessing test')
def test_real_mp4_index_retries_reuse_units(service,tmp_path):
    async def check():
        source=tmp_path/'sample.mp4'
        await command('ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc2=size=160x90:rate=5',
            '-t','4','-c:v','libx264','-pix_fmt','yuv420p',str(source))
        r=service.stage(source,'cam-a',1000)
        service.embedding.fail_at=3
        failed=await service.index(r['id'])
        assert failed['status']=='failed'
        assert not service.index_db.recall(vec(),service.index_signature)[0]
        service.embedding.fail_at=None
        ready=await service.index(r['id'])
        assert ready['status']=='ready'
        # First video/frame succeeded before failure. They are reused on retry.
        video_calls=[call for call in service.embedding.calls if call.get('video')]
        assert len(video_calls)==1
        assert len(service.embedding.calls)==5
        result=await finish(service,dict(text='画面'))
        assert result['videos'] and result['videos'][0]['recordedAt']==1000
        assert service.retrieval.thumbnail(result['id'],result['videos'][0]['id'],'alice').is_file()
    asyncio.run(check())


def test_tool_preserves_authorized_image_and_rejects_model_invented_ref(service):
    async def check():
        indexed(service)
        image=service.retrieval.upload_image('alice',jpeg())
        tools=build_tools(service.store,AsyncMock(),execution_mode='history',video_service=service,run={'referenceImageId':image['id'],'clientId':'alice','message':'有人将参考物体放到门边'})
        # Host scope, not a model-created owner argument, binds the reference.
        value=await tools.call('search_recordings',query='寻找此外观')
        assert value['videos'][0]['referenceImageUsed']
        assert service.embedding.calls[-1]['text']=='有人将参考物体放到门边'
        assert service.vision.calls[-1][1]=='有人将参考物体放到门边'
        with pytest.raises(ValueError): await tools.call('search_recordings',query='物体',image_ref='query-image-'+'0'*32)
    asyncio.run(check())


def test_cache_bounded_filtered_and_invalidated(service,monkeypatch):
    import evidenceguard.video.index_v2 as module
    indexed(service,'video-a','cam-a');indexed(service,'video-b','cam-b',vector=vec(1))
    hits,_=service.index_db.recall(vec(),service.index_signature,cameras={'cam-a'})
    assert {h['clip']['recordingId'] for h in hits}=={'video-a'} and service.index_db.cache_size>0
    hits,_=service.index_db.recall(vec(),service.index_signature,cameras={'cam-b'})
    assert {h['clip']['recordingId'] for h in hits}=={'video-b'}
    service.index_db.delete('video-b')
    assert service.index_db.cache_size==0
    assert not service.index_db.recall(vec(),service.index_signature,cameras={'cam-b'})[0]
    monkeypatch.setattr(module,'CACHE_BYTES',4096)
    service.index_db.recall(vec(),service.index_signature,cameras={'cam-a'})
    assert service.index_db.cache_size<=4096


def test_read_only_dashboard_understands_binary_active_vectors(service):
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'dashboard'))
    from eg_dashboard.media import read_media
    indexed(service);indexed(service,signature='unfinished',publish=False)
    path=service.store.db.execute('PRAGMA database_list').fetchone()[2]
    rows,summary=read_media(Path(path),time.time(),service.index_signature)
    vectors=[r['data'] for r in rows if r['name']=='media_video_segments']
    assert len(vectors)==2 and all(v['indexVersion']==2 and v['normalized'] for v in vectors)
    assert summary['tables']['retrieval_embeddings']['matchingSignature']==2
    assert str(service.root) not in json.dumps(rows)
    assert 'unfinished' not in json.dumps(rows)


def test_evaluator_rejects_split_leakage_and_keeps_failures_in_totals():
    from evidenceguard.video.evaluate_search import validate,summarize
    a=dict(id='a',mode='text',text='包裹',split='tuning',event_group='one',expected=[dict(recording_id='video-one',start=1,end=2,kind='action')])
    b=a|dict(id='b',split='held_out',event_group='two')
    with pytest.raises(ValueError): validate([a,b])
    b['expected']=[];b['event_group']='one'
    with pytest.raises(ValueError): validate([a,b])
    rows=[dict(mode='text',split='held_out',status='failed',expectedByKind={'action':1},foundByKind={},
        matched=0,correctlyLocated=0,negative=False,falseConfirmation=False,verificationFailed=1,uncertain=0)]
    summary=summarize(rows)['held_out']
    assert summary['recallAt10']['action']==0 and summary['failedQueries']==1 and summary['failedVerifications']==1
    assert not summary['minimumQueryCountMet']


def test_reindex_complete_version_is_idempotent(service):
    async def check():
        indexed(service)
        before=service.index_db.generation
        result=await service.index('video-one')
        assert result['status']=='ready' and not service.embedding.calls
        assert service.index_db.generation==before
    asyncio.run(check())


def test_failed_upgrade_can_roll_back_to_legacy_text_index(service,monkeypatch):
    async def check():
        r,clip=indexed(service)
        service.index_db.delete(r['id'])
        r.update(embeddingSignature=service.embedding.signature,embeddingModel=service.embedding.model)
        clip['signature']=service.embedding.signature
        service.db.publish(r,[(clip,vec())])
        # No original media in this fixture: the attempted upgrade fails.
        service.start_index(r['id']);await service.jobs[r['id']]
        assert service.db.recording(r['id'])['status']=='failed'
        monkeypatch.setenv('EG_VIDEO_INDEX_V2','0')
        service.embedding.embed=AsyncMock(return_value=vec())
        assert service.public(service.db.recording(r['id']))['status']=='ready'
        result=await service.search('这个物体')
        assert result['videos'][0]['verdict']=='matched'
    asyncio.run(check())


def test_private_search_observability_keeps_only_metadata(tmp_path):
    from evidenceguard.ops import Recorder,RECORDER,PRIVATE_CONTENT,model_post
    recorder=Recorder(tmp_path/'ops.sqlite',capture=True)
    async def check():
        token=RECORDER.set(recorder);privacy=PRIVATE_CONTENT.set(True)
        try:
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'usage':{'total_tokens':7}}))) as client:
                await model_post(client,'https://model.test/chat',headers={},json=dict(model='vision-test',messages=[dict(role='user',content='private-reference-text')]))
                recorder.emit('test',data={'reference_image':'private-image-path','text':'private-reference-text','completed':1})
        finally: PRIVATE_CONTENT.reset(privacy);RECORDER.reset(token)
    asyncio.run(check());recorder.flush()
    rows=[json.loads(row[0]) for row in recorder.db.execute('SELECT payload FROM records')]
    assert 'private-reference-text' not in json.dumps(rows) and 'private-image-path' not in json.dumps(rows)
    assert any(row['data'].get('httpStatus')==200 for row in rows)
    assert all(row['data']['privateContent'] for row in rows)
    recorder.close()
