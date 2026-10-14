from __future__ import annotations
import asyncio, os, re, time
from contextlib import asynccontextmanager
from pathlib import Path
import httpx
from typing import Literal
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Response, Request, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uuid
from pydantic import BaseModel, Field
from .camera.adapters.fixture_lab import FixtureLabAdapter
from .camera.registry import CameraRegistry, EmptyCameraAdapter
from .camera.live import LiveDevices
from .camera.live_routes import install_live_routes
from .camera.service import CameraService
from .harness.scheduler import TaskScheduler
from .harness.runtime import AgentRuntime
from .harness.tools import build_tools
from .history import HistoryFilter
from .schemas import EditSkill
from .store import Store, CameraConflict
from .worker import ObservationWorker
from .video.service import VideoService, command
from .camera.adapters.replay import ReplayAdapter
from .replay import ReplayWorker
from .skill_capabilities import assess, CATALOG
from .skill_trials import SkillTrials
from .deployment import SitePreparation
from .access import install_access
from .personal import PersonalAgent, Preferences, MemoryInput, installation
from .proactive import ProactiveEngine, Feedback, BindConversation
from .visual_review import VisualReview
from .camera.ingest import SDKIngest, SDKBatch
from .conversations import Conversations, NewConversation, ConversationTitle
from .demo_scene import DemoScenes, SceneRequest

if os.getenv('EG_ENV_FILE'): load_dotenv(os.environ['EG_ENV_FILE'],override=False)
class ConfirmRequest(BaseModel):
    revision: int = Field(ge=1)
    fixtureAcknowledged: bool = False
    replayAcknowledged: bool = False
    switchFrom: dict[str, str] = Field(default_factory=dict)
    trialId: str | None = None
    trialReviewed: bool = False
class LifecycleRequest(BaseModel):
    action: Literal['pause','resume','stop']
    switchFrom: dict[str,str] = Field(default_factory=dict)
class AgentRequest(BaseModel):
    message: str = Field(min_length=1,max_length=2000)
    conversationId: str = Field(min_length=1,max_length=100)
    requestId: str = Field(min_length=1,max_length=100)
    skillId: str | None = None
    cameraId: str | None = None
    executionMode: Literal['live','history'] = 'live'
    historyFilter: HistoryFilter | None = None
    replyToMessageId: str | None = Field(default=None,max_length=100)
class RecheckRequest(BaseModel): acknowledged: bool = False
class ReplayTransport(BaseModel): online: bool
class ManualDraftRequest(BaseModel):
    cameraId: str
    conversationId: str = Field(min_length=1,max_length=100)
    prompt: str = Field(default='请选择画面中的观察对象并完善提醒条件',min_length=2,max_length=2000)
    replacesId: str | None = None

class TrialRequest(BaseModel):
    revision: int = Field(ge=1)
    expectedOutcome: Literal['explore','alert','no_alert'] = 'explore'
class PreparationRequest(BaseModel):
    revision: int = Field(ge=1)
    action: str
    completed: bool


def create_app(db_path=None,seed=False,start_worker=True,provider=None,camera_adapter=None):
    root=Path(__file__).resolve().parents[2]
    store=Store(db_path or Path(os.getenv('EG_DATABASE',str(root/'data/evidenceguard.sqlite3'))))
    store.recover_ownership()
    personal = PersonalAgent(store)
    camera=CameraRegistry(camera_adapter or (FixtureLabAdapter(os.getenv('EVIDENCEGUARD_FIXTURE_URL','http://127.0.0.1:8787')) if os.getenv('EG_CAMERA_MODE') == 'fixture' else EmptyCameraAdapter()))
    camera.live=LiveDevices(store)
    scheduler=TaskScheduler()
    captures=CameraService(store,camera,scheduler)
    database=Path(store.db.execute('PRAGMA database_list').fetchone()[2])
    videos=VideoService(store,os.getenv('EG_VIDEO_ROOT',str(database.parent/'recordings')))
    videos.recover()
    camera.replay=ReplayAdapter(videos)
    replay_worker=ReplayWorker(store,videos,captures)
    trials=SkillTrials(store,videos)
    preparation=SitePreparation(store)
    tools=build_tools(store,camera,captures,video_service=videos); agent=AgentRuntime(store,tools,provider,camera,scheduler)
    proactive=ProactiveEngine(personal,agent)
    conversations=Conversations(store,proactive)
    visual_review=VisualReview(store,videos.vision)
    agent.visual_review=visual_review
    replay_worker.visual_budget=visual_review
    ingest=SDKIngest(store,visual_review,personal)
    proactive.ingest=ingest
    demo=DemoScenes(store,visual_review,proactive)
    proactive.demo=demo
    worker=ObservationWorker(store,camera,camera_service=captures,scheduler=scheduler,replay_worker=replay_worker)
    @asynccontextmanager
    async def lifespan(_):
        task=asyncio.create_task(worker.run()) if start_worker else None
        personal_task=asyncio.create_task(proactive.run()) if start_worker else None
        ingest_task=asyncio.create_task(ingest.run()) if start_worker else None
        demo_task=asyncio.create_task(demo.run()) if start_worker and demo.enabled else None
        try: yield
        finally:
            if demo_task:
                demo_task.cancel(); await asyncio.gather(demo_task,return_exceptions=True)
            if ingest_task:
                ingest_task.cancel(); await asyncio.gather(ingest_task,return_exceptions=True)
            if personal_task:
                personal_task.cancel(); await asyncio.gather(personal_task, return_exceptions=True)
            await trials.shutdown()
            await agent.shutdown()
            if task:
                task.cancel(); await asyncio.gather(task,return_exceptions=True)
            await worker.shutdown()
            await videos.shutdown()
            await scheduler.shutdown()
            await camera.live.shutdown()
            store.close()
    app=FastAPI(title='EvidenceGuard Cloud',version='0.9.0',lifespan=lifespan)
    install_access(app)
    install_live_routes(app, camera, captures)
    app.state.store,app.state.camera,app.state.tools,app.state.agent,app.state.worker=store,camera,tools,agent,worker
    app.state.videos=videos
    app.state.replay_worker=replay_worker
    app.state.trials=trials
    app.state.personal=personal
    app.state.proactive=proactive
    app.state.ingest=ingest
    app.state.visual_review=visual_review
    app.state.demo=demo
    @app.exception_handler(KeyError)
    async def missing(request,error):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404,content={'detail':'内容不存在或已移除'})
    @app.exception_handler(ValueError)
    async def invalid(request,error):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=409,content={'detail':str(error)[:400]})
    @app.exception_handler(CameraConflict)
    async def occupied(request,error):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=409,content={'detail':str(error),'code':'camera_occupied','conflicts':error.conflicts})
    @app.get('/api/health')
    async def health(): return dict(status='ok',workerError=worker.last_error,modelReady=agent.ready)
    @app.get('/api/bootstrap')
    async def bootstrap(request: Request):
        manifests=await camera.manifests()
        skills=[s | {'capability':assess(s,videos,manifests)} for s in store.skills()]
        return dict(personal=personal.snapshot(installation(request.headers['X-EG-Installation-ID'])) if request.headers.get('X-EG-Installation-ID') else None,now=time.time(),summary=dict(activeSkills=sum(s['status']=='active' for s in skills),openAlerts=sum(s['alert']=='open' for s in skills),unknownSkills=sum(s['result']=='unknown' and s['status']=='active' for s in skills)),skills=skills,cameras=[m.api_dict() for m in manifests],evidence=[{k:v for k,v in e.items() if k!='videoPath'} for e in store.evidence()],agent=dict(provider=agent.provider,mode=agent.mode,ready=agent.ready,tools=tools.names),integration=dict(lab='fixture-lab/v1',officialSdk='received; physical integration pending',physicalDevicesValidated=False),recordings=[videos.public(r) for r in videos.db.recordings()[:100]],videoModels=dict(visionModel=videos.vision.model,embeddingModel=videos.embedding.model,embeddingReady=videos.embedding.ready))
    def personal_client(request): return installation(request.headers.get('X-EG-Installation-ID'))
    @app.get('/api/demo/scenes')
    async def demo_scenes(request: Request): return demo.snapshot(personal_client(request))
    @app.post('/api/demo/scenes',status_code=202)
    async def demo_start(body: SceneRequest,request: Request): return demo.start(personal_client(request),body)
    @app.post('/api/sdk/events',status_code=202)
    async def sdk_ingest(request: Request):
        client=personal_client(request)
        raw=bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw)>8_000_000: raise HTTPException(413,'单批事件上限为8MB，请分批上传')
        return ingest.accept(SDKBatch.model_validate_json(bytes(raw)),client)
    @app.get('/api/sdk/events/status')
    async def sdk_status(): return ingest.status()
    @app.get('/api/personal')
    async def personal_read(request: Request): return personal.snapshot(personal_client(request))
    @app.put('/api/personal/preferences')
    async def personal_preferences(request: Request, body: Preferences): return personal.preferences(personal_client(request), body)
    @app.post('/api/personal/memories', status_code=201)
    async def personal_remember(request: Request, body: MemoryInput): return personal.remember(personal_client(request), body)
    @app.delete('/api/personal/memories/{key}')
    async def personal_forget(request: Request, key: str): return personal.forget(personal_client(request), key)
    @app.post('/api/personal/inbox/{key}/read')
    async def personal_mark_read(request: Request, key: str): return personal.read(personal_client(request), key)
    @app.put('/api/personal/conversation')
    async def bind_personal_conversation(request: Request, body: BindConversation):
        return conversations.bind_main(personal_client(request),body.conversationId)
    @app.post('/api/personal/messages/{key}/feedback')
    async def personal_feedback(request: Request, key: str, body: Feedback):
        return proactive.feedback(personal_client(request),key,body.action)
    @app.get('/api/recordings/{recording_id}')
    async def recording(recording_id:str):
        r=videos.db.recording(recording_id)
        if not r.get('aspectRatio'):
            import json
            value=json.loads(await command('ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height','-of','json',str(videos.file(recording_id))))['streams'][0]
            r['aspectRatio']=value['width']/value['height']; videos.db.save_recording(r)
        return videos.public(r)
    @app.api_route('/api/recordings/{recording_id}/video',methods=['GET','HEAD'])
    async def play_recording(recording_id:str):
        # FileResponse implements byte Range/206, needed by AVPlayer for seeking.
        return FileResponse(videos.file(recording_id),media_type='video/mp4',headers={'Cache-Control':'private, max-age=3600'})
    @app.get('/api/recordings/{recording_id}/preview')
    async def recording_preview(recording_id:str):
        source=videos.file(recording_id)
        raw=await command('ffmpeg','-hide_banner','-loglevel','error','-protocol_whitelist','file,pipe','-i',str(source),'-frames:v','1','-f','image2pipe','-vcodec','mjpeg','pipe:1')
        return Response(raw,media_type='image/jpeg',headers={'Cache-Control':'private, max-age=3600'})
    def replay_evidence(evidence_id):
        with store.lock: row=store.db.execute('SELECT payload FROM evidence WHERE id=?',(evidence_id,)).fetchone()
        import json
        item=json.loads(row[0]) if row else None
        if not item or item.get('sourceType')!='replay' or not item.get('videoPath'): raise KeyError(evidence_id)
        return item
    @app.get('/api/replay-evidence/{evidence_id}')
    async def replay_metadata(evidence_id:str):
        e=replay_evidence(evidence_id)
        return dict(id=e['id'],cameraId=e['cameraId'],title='回放提醒证据',recordedAt=e['recordedAt']+e['clipStart'] if e.get('recordedAt') is not None else None,
            sourceType='replay',timestampMeaning=e.get('timestampMeaning'),status='evidence',duration=e['clipEnd']-e['clipStart'],segmentCount=1,error=None,playbackUrl=e['videoUrl'])
    @app.api_route('/api/replay-evidence/{evidence_id}/video',methods=['GET','HEAD'])
    async def replay_video(evidence_id:str):
        return FileResponse(replay_evidence(evidence_id)['videoPath'],media_type='video/mp4')
    @app.post('/api/skills/{skill_id}/replay-acknowledge')
    async def replay_acknowledge(skill_id:str):
        with store.transaction():
            s=store.skill(skill_id)
            if not s or not s.get('replay') or s['status']!='completed': raise ValueError('只有已结束的回放提醒可以标记已核验')
            if s['alert']=='open':
                s['alert']='acknowledged';store.save_skill(s)
                store.event(skill_id,'replay_acknowledged',{'evidenceRetained':True})
            return s
    @app.post('/api/skills/{skill_id}/replay-transport')
    async def replay_transport(skill_id:str,body:ReplayTransport): return await replay_worker.transport(skill_id,body.online)
    @app.post('/api/recordings/{recording_id}/index',status_code=202)
    async def reindex(recording_id:str):
        videos.start_index(recording_id)
        return videos.public(videos.db.recording(recording_id))
    @app.post('/api/recordings',status_code=202)
    async def upload_recording(request:Request,cameraId:str,title:str=Query(default='导入录像',max_length=100),recordedAt:float|None=None):
        if cameraId not in {m.id for m in await camera.manifests()}: raise ValueError('请为录像选择已配置的摄像头')
        if len(videos.jobs)>=3: raise ValueError('已有多段录像排队，请稍后上传')
        incoming=videos.root/('upload-'+uuid.uuid4().hex); size=0
        try:
            with incoming.open('wb') as file:
                async for chunk in request.stream():
                    size+=len(chunk)
                    if size>150_000_000: raise HTTPException(413,'当前录像上限为 150 MB')
                    file.write(chunk)
            value=videos.stage(incoming,cameraId,recordedAt,title)
            videos.start_index(value['id'])
            return videos.public(value)
        finally: incoming.unlink(missing_ok=True)
    @app.post('/api/skills/drafts',status_code=201)
    async def manual_draft(body:ManualDraftRequest):
        manifests=await camera.manifests()
        if body.cameraId not in {m.id for m in manifests}:raise ValueError('请选择已配置的摄像头')
        if body.replacesId:
            previous=store.skill(body.replacesId)
            if not previous or body.cameraId not in previous['devices']:raise ValueError('修改来源与摄像头不匹配')
        value=store.create_draft(body.prompt,[body.cameraId],name='待配置的画面守护',target_description='请圈选并描述观察对象',replaces_id=body.replacesId)
        value.pop('replay',None)  # This entry starts from a live camera, never silently inherits an old recording.
        value['originConversationId']=body.conversationId
        store.save_skill(value)
        return value | {'capability':assess(value,videos,manifests)}
    @app.get('/api/skill-capabilities')
    async def capability_catalog(): return CATALOG
    @app.get('/api/skills/{skill_id}/capability')
    async def capability(skill_id:str):
        s=store.skill(skill_id)
        if not s:raise KeyError(skill_id)
        return assess(s,videos,await camera.manifests())
    @app.get('/api/skills/{skill_id}/deployment')
    async def deployment(skill_id:str):
        s=store.skill(skill_id)
        if not s:raise KeyError(skill_id)
        return preparation.read(s,await camera.manifests())
    @app.post('/api/skills/{skill_id}/deployment/preparation')
    async def prepare_site(skill_id:str,body:PreparationRequest):
        s=store.skill(skill_id)
        if not s:raise KeyError(skill_id)
        return preparation.update(s,body.revision,body.action,body.completed,await camera.manifests())
    @app.post('/api/skills/{skill_id}/publish')
    async def publish(skill_id:str):
        s=store.skill(skill_id)
        if not s:raise KeyError(skill_id)
        result=preparation.read(s,await camera.manifests())
        raise ValueError('真机发布未就绪：'+'；'.join(result['blockers']))
    @app.post('/api/skills/{skill_id}/trials',status_code=202)
    async def start_trial(skill_id:str,body:TrialRequest):return trials.start(skill_id,body.revision,body.expectedOutcome)
    @app.get('/api/skills/{skill_id}/trials')
    async def trial_list(skill_id:str):return [trials.public(r) for r in trials.list(skill_id)]
    @app.get('/api/skill-trials/{trial_id}')
    async def trial_report(trial_id:str):return trials.public(trials.read(trial_id))
    @app.post('/api/skill-trials/{trial_id}/cancel')
    async def cancel_trial(trial_id:str):return await trials.cancel(trial_id)
    @app.get('/api/skill-trials/{trial_id}/recording')
    async def trial_recording(trial_id:str):
        r=trials.read(trial_id)
        if not r.get('videoPath'):raise KeyError(trial_id)
        s=store.skill(r['skillId'])
        return dict(id=r['id'],cameraId=r['cameraId'],title='试跑片段 · 不是真实告警',recordedAt=None,sourceType='trial',timestampMeaning=r.get('timestampMeaning'),status='evidence',duration=r['clipEnd']-r['clipStart'],segmentCount=1,error=None,playbackUrl=r['videoUrl'])
    @app.api_route('/api/skill-trials/{trial_id}/video',methods=['GET','HEAD'])
    async def trial_video(trial_id:str):
        r=trials.read(trial_id)
        if not r.get('videoPath'):raise KeyError(trial_id)
        return FileResponse(r['videoPath'],media_type='video/mp4')
    @app.patch('/api/skills/{skill_id}')
    async def edit(skill_id:str,body:EditSkill):
        known={m.id for m in await camera.manifests()}
        if not set(body.devices)<=known: raise ValueError('无效的摄像头选择')
        value=store.edit(skill_id,body)
        return value | {'capability':assess(value,videos,await camera.manifests())}
    @app.post('/api/skills/{skill_id}/confirm')
    async def confirm(skill_id:str,body:ConfirmRequest):
        async with captures.transition():
            return await confirm_locked(skill_id,body)
    async def confirm_locked(skill_id,body):
        s=store.skill(skill_id)
        if not s: raise KeyError(skill_id)
        assessment=assess(s,videos,await camera.manifests())
        if not assessment['canActivate']:raise ValueError('；'.join(assessment['blockers']))
        if s.get('replay'):
            trials.require_review(s,body.trialId,body.trialReviewed)
            if not body.replayAcknowledged: raise ValueError('请确认这是录像回放测试，不是真实摄像头守护')
            r=videos.db.recording(s['replay']['recordingId'])
            if len(s['devices'])!=1 or s['target']['cameraId']!=s['devices'][0] or r['cameraId']!=s['devices'][0]: raise ValueError('回放仅支持录像所属的单台摄像头')
            if not r.get('duration') or not 2<=r['duration']<=60: raise ValueError('回放测试使用 2–60 秒已导入录像')
            videos.file(r['id'])
            if not videos.vision.ready: raise ValueError('视频模型未配置')
            if s['rules']['trigger']!='leaves_region': raise ValueError('回放仅验证包裹区域状态变化')
            if not s['rules']['saveEvidence']: raise ValueError('回放提醒必须保留视频证据')
            with store.transaction():
                latest=store.skill(skill_id)
                if latest['revision']!=body.revision: raise ValueError('草案已变化，请重新确认')
                if latest['status']!='active':
                    latest['replayState']={'cursor':0,'online':True,'modelCalls':0,'generation':0}
                    latest['targetBinding']={'detector':'parcel-samples/v2'};latest['approvedTrialId']=body.trialId;store.save_skill(latest)
                    store.event(skill_id,'trial_reviewed',{'trialId':body.trialId,'revision':body.revision})
                return store.confirm(skill_id,body.revision,body.switchFrom)
        if not body.fixtureAcknowledged: raise ValueError('当前仅连接测试摄像头，请先确认使用测试标记验证规则')
        if s.get('rules',{}).get('trigger')=='record_activity': raise ValueError('活动录像执行器尚未接入，草案已保留，暂不能启用')
        manifests={m.id:m for m in await camera.manifests()}
        if any(d not in manifests or manifests[d].connection!='online' for d in s['devices']): raise ValueError('所选摄像头未就绪，请恢复连接后重试')
        if s['status']=='active': return store.confirm(skill_id,body.revision,body.switchFrom)
        state=await camera.state()
        observations={c['id']:c.get('observation') for c in state.get('cameras',[])}
        obs=observations.get(s['target']['cameraId'])
        box=s['target']['box']
        if not obs or 17 not in obs.get('marker_ids',[]) or not obs.get('bbox') or not 0<=time.time()-obs['captured_at']<6:
            raise ValueError('主视角还没有清晰的新鲜目标画面，请重新观察后确认')
        x1,y1,x2,y2=obs['bbox']; cx,cy=(x1+x2)/2,(y1+y2)/2
        if not (box['x']<=cx<=box['x']+box['width'] and box['y']<=cy<=box['y']+box['height']):
            raise ValueError('橙色目标框未圈住测试标记，请先圈选当前画面中的目标')
        with store.transaction():
            # Re-read after awaiting camera I/O to enforce the user's confirmed revision.
            latest=store.skill(skill_id)
            if latest['revision']!=body.revision: raise ValueError('草案已变化，请重新确认')
            latest['viewRevisions']={d:str(observations[d].get('revision','unknown')) for d in s['devices'] if observations.get(d)}
            latest['targetBinding']={'detector':'fixture-marker/v1','markerId':17,'referenceFrameId':obs['frame_id']}
            store.save_skill(latest)
            return store.confirm(skill_id,body.revision,body.switchFrom)
    @app.get('/api/skills/{skill_id}/conflicts')
    async def conflicts(skill_id:str):
        s=store.skill(skill_id)
        if not s: raise KeyError(skill_id)
        return store.conflicts(s)
    @app.post('/api/skills/{skill_id}/lifecycle')
    async def lifecycle(skill_id:str,body:LifecycleRequest):
        async with captures.transition():
            return store.lifecycle(skill_id,body.action,body.switchFrom)
    @app.post('/api/skills/{skill_id}/recheck')
    async def recheck(skill_id:str,body:RecheckRequest):
        if (store.skill(skill_id) or {}).get('replay'): raise ValueError('回放不重看未来或已过片段；请查看证据，或暂停后恢复重新建立基线')
        value=store.recheck(skill_id,body.acknowledged)
        store.event(skill_id,'recheck_requested',{'notBefore':value['notBefore']})
        return store.skill(skill_id)
    def conversation_access(conversation_id, request):
        client=personal_client(request) if request.headers.get('X-EG-Installation-ID') else None
        conversations.check(conversation_id,client)
    def run_access(run_id, request):
        value=store.run(run_id)
        if not value: raise KeyError(run_id)
        if value.get('clientId') and value['clientId']!=personal_client(request): raise HTTPException(404,'请求不存在')
        conversation_access(value['conversationId'],request)
        return value
    @app.post('/api/agent/runs',status_code=202)
    async def start(body:AgentRequest,request:Request):
        conversation_access(body.conversationId,request)
        if store.run(body.requestId): run_access(body.requestId,request)
        client=personal_client(request) if request.headers.get('X-EG-Installation-ID') else None
        context=personal.context(client)
        if context and proactive.owner(body.conversationId)==client:
            # Independent assistant messages are actual history, not invented user prompts.
            context['proactiveMessages']=[{k:m.get(k) for k in ('id','body','why','createdAt','feedback')} for m in proactive.messages(client)[-8:]]
        if body.replyToMessageId:
            reply=next((m for m in proactive.messages(client) if m['id']==body.replyToMessageId),None) if client else None
            if not reply or proactive.owner(body.conversationId)!=client: raise HTTPException(404,'要回复的主动消息不存在')
            context['replyToMessage']={k:reply.get(k) for k in ('id','body','why','sources','createdAt','feedback')}
        value=agent.start(body.message,body.conversationId,body.skillId,body.requestId,body.cameraId,body.executionMode,body.historyFilter.model_dump() if body.historyFilter else None,personal_context=context,reply_to=body.replyToMessageId)
        if client: value['clientId']=client; store.save_run(value)
        return value
    @app.get('/api/agent/conversations')
    async def conversation_list(request:Request):
        return conversations.listing(personal_client(request))
    @app.post('/api/agent/conversations',status_code=201)
    async def conversation_create(body:NewConversation,request:Request):
        return conversations.create(personal_client(request),body.requestId)
    @app.patch('/api/agent/conversations/{conversation_id}')
    async def conversation_rename(conversation_id:str,body:ConversationTitle,request:Request):
        return conversations.rename(conversation_id,personal_client(request),body.title)
    @app.get('/api/agent/conversations/{conversation_id}')
    async def conversation(conversation_id:str,request:Request):
        conversation_access(conversation_id,request)
        client=personal_client(request) if request.headers.get('X-EG-Installation-ID') else None
        return [r for r in store.runs(conversation_id) if not r.get('clientId') or r['clientId']==client]
    @app.get('/api/runs/{run_id}')
    async def run(run_id:str,request:Request): return run_access(run_id,request)
    @app.post('/api/runs/{run_id}/cancel')
    async def cancel(run_id:str,request:Request):
        value=run_access(run_id,request)
        if value.get('initiator')=='agent': raise ValueError('请在主动消息中选择处理方式，或关闭主动提醒')
        return await agent.cancel(run_id)
    @app.get('/api/runs/{run_id}/events')
    async def events(run_id:str,request:Request,after:int=0):
        run_access(run_id,request)
        return store.events(run_id,after)
    @app.get('/api/media/{media_id}')
    async def media(media_id:str):
        if not re.fullmatch(r'[a-f0-9]{64}',media_id): raise HTTPException(404,'media not found')
        raw,mime,_=store.media(media_id)
        return Response(raw,media_type=mime,headers={'Cache-Control':'private, max-age=86400'})
    @app.get('/api/skills/{skill_id}/events')
    async def skill_events(skill_id:str,after:int=0):
        if not store.skill(skill_id): raise KeyError(skill_id)
        return store.events(skill_id,after)
    @app.get('/api/camera/frames/{device_id}/{filename}')
    async def frame(device_id:str,filename:str):
        fid=filename.removesuffix('.jpg')
        if not re.fullmatch(r'[a-z0-9-]+',fid): raise HTTPException(404,'frame not found')
        try: raw,mime=await camera.frame_bytes(device_id,fid)
        except (ValueError,RuntimeError,httpx.HTTPError): raise HTTPException(404,'画面已不可用，请重新观察')
        return Response(raw,media_type=mime,headers={'Cache-Control':'private, max-age=2'})
    # The same API serves SwiftUI and the optional Web build. API routes take
    # precedence; unknown API paths remain 404 rather than returning the SPA.
    web_setting = os.getenv('EG_WEB_ROOT')
    web_root = Path(web_setting) if web_setting else None
    if web_root is not None and (web_root/'index.html').is_file():
        app.mount('/', StaticFiles(directory=web_root, html=True), name='web')
    return app

app=create_app()
