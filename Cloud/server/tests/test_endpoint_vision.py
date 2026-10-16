"""Read-only SeedLite host contract, using synthetic pixels and scripted models."""
import asyncio
import io
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from evidenceguard.store import Store
from evidenceguard.visual_review import VisualReview
from evidenceguard.vision.endpoints import EndpointVisionService


def picture(store, key, at, **changes):
    output=io.BytesIO(); Image.new('RGB',(96,64),'blue').save(output,format='PNG')
    meta=dict(device_id='sdk-test',frame_id=key,channel_id='main',view_revision='live-test:0',
              captured_at=None,sampled_at=at,received_at=at+.01,source_type='official_live_ios',
              freshness='sampled_after_request',request_id='request-'+key,session_id='live-test',execution_epoch='epoch-test')
    meta.update(changes)
    item=store.save_media(meta,output.getvalue(),'image/png')
    return dict(status='completed',mediaId=item['id'],frameId=key,cameraId='sdk-test',viewRevision=meta['view_revision'],
                sourceType=meta['source_type'],sampledAt=at,capturedAt=None,imageUrl=item['imageUrl'])


def answer(scene, current):
    target=scene['id']+':'+str(scene['revision'])
    def observation(frame):
        return dict(frame_id=frame['frameId'],camera_id='main',target_id=target,presence='visible',
                    correspondence='confirmed',roi_state='inside',region_visibility='clear',occupancy='occupied',evidence='区域内可见蓝色物体')
    return dict(observations={'a':observation(scene['frame']),'b':observation(current)},spatial_relations=[],
                cross_frame=dict(state_change='no_observed_change',image_direction='stationary',motion_basis='rgb',
                                 physical_motion='unknown',action_claim='unknown',continuous_tracking_supported=False,
                                 speed=None,distance_m=None,evidence=['两端均可见'],unknowns=['中间过程未知'],next_evidence=[]),
                summary='两端可见蓝色物体，中间过程未知。')


@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setenv('EG_ENDPOINT_ENABLED','1')
    for key,value in [('BASE_URL','https://example.invalid/api/v3'),('MODEL_ID','doubao-seed-2-1-lite-260915'),('API_KEY','test-only-not-real')]:
        monkeypatch.setenv('EG_ENDPOINT_'+key,value)
    store=Store(tmp_path/'endpoints.sqlite')
    visual=VisualReview(store,SimpleNamespace(ready=False))
    service=EndpointVisionService(store,visual)
    now=time.time()
    scene=dict(id='scene-test',clientId='installation-test',cameraId='sdk-test',revision=2,status='active',stage='review',
               frame=picture(store,'baseline',now-20),plan=dict(target='蓝色物体',selection='object'),
               box=dict(x=.1,y=.1,width=.4,height=.4))
    current=picture(store,'current',now-1)
    service.port._request=AsyncMock(return_value={'content':json.dumps(answer(scene,current),ensure_ascii=False)})
    yield service,scene,current,visual
    store.db.close()


def test_one_rgb_call_originals_and_crops_scope_metadata_and_cached_receipt(setup):
    async def run():
        service,scene,current,visual=setup
        result=await service.analyze(scene,current,lambda:True)
        assert result['status']=='completed' and not result['controlEligible'] and not result['isLiveConclusion']
        assert result['sources']['a']['captured_at'] is None
        assert result['sources']['b']['camera_id']=='main'
        assert result['sources']['b']['device_id']=='sdk-test'
        assert result['sources']['b']['timestampMeaning']=='client_live_sample'
        assert result['sources']['b']['execution_epoch']=='epoch-test'
        messages=service.port._request.call_args.args[0]
        parts=messages[1]['content']
        assert sum(p['type']=='image_url' for p in parts)==4
        assert 'test-only-not-real' not in json.dumps(messages)
        assert 'truth' not in json.dumps(messages)
        again=await service.analyze(scene,current,lambda:True)
        assert again['cached'] and again['createdAt']==result['createdAt']
        assert service.port._request.await_count==1
        assert visual.usage('sdk-test')['requests']==1
    asyncio.run(run())


def test_depth_images_are_actually_sent_and_cache_is_separate_from_rgb(setup):
    import base64
    from evidenceguard.vision.processing import LocalVision
    async def check():
        service,scene,current,_=setup
        rgb=await service.analyze(scene,current,lambda:True)
        data,_,_=service.store.media(current['mediaId'])
        service.local.configuration=lambda:dict(ready=True,depthReady=True,flowReady=True)
        service.local.analyze=AsyncMock(return_value=dict(status='completed',depth={'status':'completed'},
            flow={'status':'skipped','code':'FRAMES_NOT_ADJACENT'},images=[dict(label='depth '+k,base64=base64.b64encode(data).decode()) for k in ('a','b')]))
        depth=await service.analyze(scene,current,lambda:True,include_depth=True)
        assert depth['status']=='completed' and depth['condition']=='C' and depth['id']!=rgb['id']
        parts=service.port._request.call_args.args[0][1]['content']
        assert sum(p['type']=='image_url' for p in parts)==6
        assert depth['auxiliary']['depth']['status']=='completed' and not depth['controlEligible']
        assert 'images' not in depth['auxiliary']
    asyncio.run(check())


@pytest.mark.parametrize('kind',['channel','view','camera','frame','time','source','same','missing','depth'])
def test_invalid_sources_cannot_call_model_or_authorize_control(setup,kind):
    service,scene,current,_=setup
    async def checked():
        nonlocal current
        updates={'channel':{'channel_id':'invented-lower'},'view':{'view_revision':'live-test:1'},
                 'camera':{'device_id':'another-device'},'time':{'sampled_at':time.time()-60},
                 'source':{'source_type':'official_sdk'}}
        if kind in updates: current=picture(service.store,'bad',time.time()-1,**updates[kind])
        if kind=='frame': current=current | {'frameId':'other-frame'}
        if kind=='same': current=scene['frame']
        if kind=='missing': current=None
        result=await service.analyze(scene,current,lambda:True,include_depth=kind=='depth')
        assert result['status']=='unknown' and not result['controlEligible']
        service.port._request.assert_not_awaited()
    asyncio.run(checked())


@pytest.mark.parametrize('change',['distance','direction','id','malformed','action'])
def test_invalid_model_claims_do_not_become_valid_analysis(setup,change):
    service,scene,current,_=setup
    value=answer(scene,current)
    if change=='distance': value['cross_frame']['distance_m']=3
    if change=='action': value['cross_frame']['action_claim']='stolen'
    if change=='id': value['observations']['b']['target_id']='invented'
    if change=='direction': value['observations']['b']['correspondence']='uncertain'
    service.port._request.return_value={'content':'not-json' if change=='malformed' else json.dumps(value)}
    result=asyncio.run(service.analyze(scene,current,lambda:True))
    assert result['status']=='unknown'
    assert service.store.db.execute('SELECT COUNT(*) FROM endpoint_analyses').fetchone()[0]==0


def test_cancel_revision_or_view_changed_during_model_discards_result(setup):
    async def run():
        service,scene,current,_=setup
        valid=True
        async def changed(*args):
            nonlocal valid
            valid=False
            return {'content':json.dumps(answer(scene,current))}
        service.port._request=changed
        result=await service.analyze(scene,current,lambda:valid)
        assert result['code']=='STALE_CONTEXT'
        assert service.store.db.execute('SELECT COUNT(*) FROM endpoint_analyses').fetchone()[0]==0
    asyncio.run(run())


def test_budget_queue_timeouts_and_cancellation_are_bounded(setup):
    async def run():
        service,scene,current,visual=setup
        service.pending=service.MAX_PENDING
        assert (await service.analyze(scene,current,lambda:True))['code']=='QUEUE_FULL'
        service.pending=0; service.MAX_WAIT=.01
        await service.lock.acquire()
        assert (await service.analyze(scene,current,lambda:True))['code']=='TIMEOUT'
        service.lock.release()
        assert service.pending==0
        visual.DAILY_LIMIT=0
        assert (await service.analyze(scene,current,lambda:True))['code']=='BUDGET_EXHAUSTED'
        assert service.port._request.await_count==0
        visual.DAILY_LIMIT=100
        async def cancelled(*args): raise asyncio.CancelledError()
        service.port._request=cancelled
        with pytest.raises(asyncio.CancelledError): await service.analyze(scene,current,lambda:True)
        assert service.pending==0 and not service.lock.locked()
    asyncio.run(run())


def test_private_context_covers_model_and_static_catalog_has_no_user_content(setup):
    from evidenceguard.ops import PRIVATE_CONTENT
    async def run():
        service,scene,current,_=setup
        async def model(*args):
            assert PRIVATE_CONTENT.get() is True
            return {'content':json.dumps(answer(scene,current))}
        service.port._request=model
        await service.analyze(scene,current,lambda:True)
        assert PRIVATE_CONTENT.get() is False
        catalog=json.dumps(service.prompt_catalog())
        assert scene['clientId'] not in catalog and current['mediaId'] not in catalog
    asyncio.run(run())


def test_partial_config_does_not_mix_with_chat_credentials(setup,monkeypatch):
    service,scene,current,visual=setup
    monkeypatch.delenv('EG_ENDPOINT_API_KEY')
    service=EndpointVisionService(service.store,visual)
    assert not service.configuration()['ready']
    assert asyncio.run(service.analyze(scene,current,lambda:True))['code']=='NOT_CONFIGURED'


def test_guard_http_and_agent_tool_share_analysis_without_capture_or_state_changes(setup,tmp_path):
    from fastapi.testclient import TestClient
    from evidenceguard.app import create_app
    from evidenceguard.visual_skills.chat import for_chat
    from evidenceguard.harness.tools import ToolRegistry
    from test_visual_scenes import PLAN,CLIENT,OTHER
    _,original,_,_=setup
    app=create_app(tmp_path/'endpoint-http.sqlite',start_worker=False)
    with TestClient(app) as client:
        scenes=app.state.visual_scenes;service=app.state.endpoint_vision;store=service.store
        now=time.time()
        scene=original | dict(clientId=CLIENT,plan=PLAN,frame=picture(store,'http-a',now-20),
            lastCapture=picture(store,'http-b',now-1),observation=scenes.empty_observation(),
            inputs=['测试'],prompt='测试',question='',unsupportedReason='',reason='',evidenceIds=[])
        with store.transaction(): scenes.save(scene,now+100)
        before=store.db.execute('SELECT due,payload FROM visual_scenes WHERE id=?',(scene['id'],)).fetchone()
        service.port._request=AsyncMock(return_value={'content':json.dumps(answer(scene,scene['lastCapture']))})
        scenes.captures.capture=AsyncMock(side_effect=AssertionError('Read-only analysis must not capture'))
        path='/api/visual-scenes/'+scene['id']+'/analyze';body={'revision':scene['revision']}
        assert client.post(path,json=body,headers={'X-EG-Installation-ID':CLIENT}).status_code==403
        owner={'X-EG-Installation-ID':CLIENT,'X-EG-Private-Key':'a'*48}
        other={'X-EG-Installation-ID':OTHER,'X-EG-Private-Key':'b'*48}
        response=client.post(path,json=body,headers=owner)
        assert response.status_code==200,response.text
        assert response.json()['status']=='completed'
        assert client.post(path,json=body,headers=other).status_code==404
        assert client.post(path,json={'revision':999},headers=owner).status_code==409
        assert client.post(path,json=body|{'mediaId':'other'},headers=owner).status_code==422
        async def invoke():
            tools=for_chat(ToolRegistry(),scenes,dict(id='read-only-run',clientId=CLIENT,cameraId='sdk-test'))
            return await tools.call('analyze_visual_endpoints',guard_id=scene['id'],revision=scene['revision'])
        result=client.portal.call(invoke)
        assert result['cached'] and result['id']==response.json()['id']
        assert before==store.db.execute('SELECT due,payload FROM visual_scenes WHERE id=?',(scene['id'],)).fetchone()
        scenes.captures.capture.assert_not_awaited()
        assert not store.skills() and not store.evidence()
        assert client.get('/api/visual-scenes/'+scene['id'],headers=owner).json().get('endpointAnalysis') is None


def test_history_contract_never_gains_endpoint_live_guard_tool(setup,tmp_path):
    from evidenceguard.app import create_app
    from test_harness import ScriptedProvider,settle
    async def check():
        app=create_app(tmp_path/'endpoint-history.sqlite',start_worker=False,
                       provider=ScriptedProvider([{'role':'assistant','content':'查询已存录像'}]))
        runtime=app.state.agent
        run=await settle(runtime,runtime.start('过去录像','history-endpoint',execution_mode='history',
            client_id='history-client',client_platform='ios',connector_access=True,guard_flow_version=1))
        assert 'analyze_visual_endpoints' not in run['executionContract']['allowed_tools']
        assert 'request_camera_snapshot' not in run['executionContract']['allowed_tools']
        await runtime.scheduler.shutdown();app.state.store.close()
    asyncio.run(check())


def test_explicit_sampling_rejects_foreign_sessions_and_view_drift(setup):
    from evidenceguard.visual_skills.service import VisualScenes
    async def check():
        service,scene,current,_=setup
        session=dict(id='live-test',client='other-client',viewVersion=0)
        live=SimpleNamespace(current=lambda _:session,recent_pair=lambda *_:None)
        capture=AsyncMock(return_value=current)
        captures=SimpleNamespace(cameras=SimpleNamespace(live=live),capture=capture)
        scenes=VisualScenes(service.store,captures,None,None)
        scenes.save(scene);scenes.endpoint_vision=service
        result=await scenes.sample_endpoints(scene['id'],scene['clientId'],scene['revision'])
        assert result['code']=='LIVE_SESSION_REQUIRED' and capture.await_count==0
        session['client']=scene['clientId']
        async def analyze(*args,**kwargs):
            assert args[2]() and kwargs['include_depth']
            session['viewVersion']=1
            return dict(status='completed')
        service.analyze=AsyncMock(side_effect=analyze)
        result=await scenes.sample_endpoints(scene['id'],scene['clientId'],scene['revision'])
        assert result['code']=='STALE_CONTEXT' and capture.await_count==2
        assert scenes.get(scene['id'],scene['clientId'])==scene
    asyncio.run(check())


def test_agent_analysis_and_followup_keep_private_content_boundary(setup,tmp_path):
    from evidenceguard.app import create_app
    from evidenceguard.ops import PRIVATE_CONTENT
    from test_harness import ScriptedProvider,settle,tool
    async def check():
        provider=ScriptedProvider([tool('analyze_visual_endpoints',dict(guard_id='test',revision=1)),
            {'role':'assistant','content':'私有分析测试正文'},
            {'role':'assistant','content':'追问仍然引用这次私有分析'}])
        app=create_app(tmp_path/'endpoint-agent.sqlite',start_worker=False,provider=provider)
        async def analyze(*args,**kwargs):
            assert PRIVATE_CONTENT.get()
            return dict(status='completed',readOnly=True,controlEligible=False,analysis={'summary':'私有分析测试正文'})
        app.state.visual_scenes.analyze_endpoints=AsyncMock(side_effect=analyze)
        privacy=[]
        original=provider.complete.side_effect
        def model(*args):
            privacy.append(PRIVATE_CONTENT.get())
            return original(*args)
        provider.complete.side_effect=model
        runtime=app.state.agent
        kwargs=dict(client_id='endpoint-client',client_platform='ios',connector_access=True,guard_flow_version=1)
        run=await settle(runtime,runtime.start('对照参考图','endpoint-chat',**kwargs))
        assert run['status']=='completed' and run['privateContent']
        assert run['endpointAnalyses'][0]['controlEligible'] is False
        follow=await settle(runtime,runtime.start('解释一下','endpoint-chat',**kwargs))
        assert follow['privateContent'] and follow['status']=='completed'
        assert privacy==[False,True,True]
        assert not PRIVATE_CONTENT.get()
        assert not app.state.store.skills() and not app.state.store.evidence()
        await runtime.scheduler.shutdown();app.state.store.close()
    asyncio.run(check())
