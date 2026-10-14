from __future__ import annotations
import asyncio, hashlib, json, math, os, shutil, time, uuid
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from .storage import VideoStore
from .providers import LiteVideoProvider, ArkVideoEmbedding, ProviderError


async def command(*args):
    process=await asyncio.create_subprocess_exec(*args,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    try:
        out,err=await asyncio.wait_for(process.communicate(),timeout=120)
    except BaseException:
        if process.returncode is None: process.kill()
        await process.communicate()
        raise
    if process.returncode: raise ValueError('视频处理失败，请检查文件是否为可读取的视频')
    return out


async def probe(path):
    value=json.loads(await command('ffprobe','-v','error','-protocol_whitelist','file,pipe','-show_entries','format=duration:stream=codec_type','-of','json',str(path)))
    duration=float(value['format']['duration'])
    if not math.isfinite(duration) or not .5<=duration<=600 or not any(s['codec_type']=='video' for s in value['streams']):
        raise ValueError('当前演示支持 0.5–600 秒的视频文件')
    return duration


def windows(duration, length=20, overlap=5):
    start=0.
    while start<duration:
        end=min(start+length,duration)
        yield start,end
        if end==duration: break
        start=end-overlap


class VideoService:
    def __init__(self,store,root,embedding=None,vision=None):
        self.store=store; self.db=VideoStore(store)
        self.root=Path(root).resolve(); self.root.mkdir(parents=True,exist_ok=True)
        self.embedding=embedding or ArkVideoEmbedding(); self.vision=vision or LiteVideoProvider()
        self.ingest_gate=asyncio.Semaphore(1); self.verify_gate=asyncio.Semaphore(2)
        self.jobs={}

    def recover(self):
        for r in self.db.recordings():
            if r['status'] in {'queued','indexing'}:
                r.update(status='interrupted',error='服务重启中断索引，请重新尝试索引'); self.db.save_recording(r)

    def public(self,r):
        value={k:v for k,v in r.items() if k not in {'sourcePath'}} | {'playbackUrl':f"/api/recordings/{r['id']}/video"}
        if r['status']=='ready' and r.get('embeddingSignature')!=self.embedding.signature:
            value.update(status='stale',error='Embedding 模型或索引策略已变化，请重新建立索引')
        return value

    def file(self,recording_id):
        r=self.db.recording(recording_id)
        path=self.root/recording_id/'playback.mp4'
        if not path.is_file(): raise KeyError(recording_id)
        return path

    def stage(self,path,camera_id,recorded_at=None,title='导入录像',source_type='uploaded',source_reference=None):
        path=Path(path).resolve()
        if not path.is_file() or not 0<path.stat().st_size<=150_000_000: raise ValueError('录像文件不存在、为空或超过 150 MB')
        if recorded_at is not None and (not math.isfinite(recorded_at) or recorded_at<0): raise ValueError('录像开始时间无效')
        # Keep a content digest for provenance; capture time is never fabricated from import time.
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        rid='video-'+uuid.uuid4().hex[:16]; folder=self.root/rid; folder.mkdir()
        shutil.copyfile(path,folder/'original')
        r=dict(id=rid,cameraId=camera_id,title=title,recordedAt=recorded_at,sourceType=source_type,
               sourceReference=source_reference,sha256=digest,createdAt=time.time(),status='queued',
               duration=None,segmentCount=0,error=None,embeddingModel=self.embedding.model)
        return self.db.save_recording(r)

    def start_index(self,rid):
        if rid in self.jobs: return
        if len(self.jobs)>=3: raise ValueError('已有多段录像排队，请稍后再试')
        r=self.db.recording(rid); r.update(status='queued',error=None); self.db.save_recording(r)
        task=asyncio.create_task(self.index(rid)); self.jobs[rid]=task
        task.add_done_callback(lambda _:self.jobs.pop(rid,None))

    async def index(self,rid):
        async with self.ingest_gate:
            r=self.db.recording(rid); r.update(status='indexing',error=None); self.db.save_recording(r)
            folder=self.root/rid; playback=folder/'playback.mp4'
            try:
                duration=await probe(folder/'original')
                r['duration']=duration; self.db.save_recording(r)
                if not playback.exists():
                    await command('ffmpeg','-hide_banner','-loglevel','error','-y','-protocol_whitelist','file,pipe','-i',str(folder/'original'),
                        '-map','0:v:0','-an','-vf',r'scale=min(960\,iw):-2','-c:v','libx264','-preset','fast','-crf','23',
                        '-pix_fmt','yuv420p','-movflags','+faststart',str(folder/'building.mp4'))
                    (folder/'building.mp4').replace(playback)
                if not self.embedding.ready: raise ProviderError('录像已保存，可播放；Embedding 尚未配置，不能完成语义索引')
                segments=[]
                for i,(start,end) in enumerate(windows(duration)):
                    clip=folder/f'segment-{i}.mp4'
                    if not clip.exists():
                        await command('ffmpeg','-hide_banner','-loglevel','error','-y','-ss',str(start),'-protocol_whitelist','file,pipe','-i',str(playback),
                            '-t',str(end-start),'-an','-c:v','libx264','-preset','fast','-crf','23','-pix_fmt','yuv420p','-movflags','+faststart',str(clip))
                    vector=await self.embedding.embed(video=clip)
                    segments.append((dict(id=rid+f'-{i}',recordingId=rid,cameraId=r['cameraId'],start=start,end=end,
                        path=str(clip),signature=self.embedding.signature),vector))
                    r['indexedSegments']=len(segments); self.db.save_recording(r)
                r.update(embeddingModel=self.embedding.model,embeddingSignature=self.embedding.signature)
                self.db.publish(r,segments)
            except asyncio.CancelledError:
                r.update(status='interrupted',error='索引被中断，可重新尝试'); self.db.save_recording(r); raise
            except Exception as error:
                r.update(status='failed',error=str(error) if isinstance(error,(ProviderError,ValueError)) else '视频索引失败，请重试')
                self.db.save_recording(r)
            return self.public(r)

    async def search(self,query,camera_id=None,skill_id=None,period=None,limit=3,history_scope=None,progress=None):
        notify=progress or (lambda *args:None)
        notify('video_search_started',{})
        if not self.embedding.ready: raise ProviderError('Embedding 尚未配置，不能执行录像语义检索')
        scope=None
        if skill_id:
            skill=self.store.skill(skill_id)
            if not skill: raise ValueError('任务不存在')
            scope=set(skill['devices'])
        recordings={r['id']:r for r in self.db.recordings(camera_id) if not scope or r['cameraId'] in scope}
        if os.getenv('EG_CAMERA_SOURCE')=='official_sdk': recordings={k:r for k,r in recordings.items() if r['sourceType']=='official_sdk'}
        now=datetime.now(ZoneInfo('Asia/Shanghai')); start_at=end_at=None
        if period:
            midnight=now.replace(hour=0,minute=0,second=0,microsecond=0)
            start_at=(midnight-timedelta(days=1) if period=='yesterday' else now-timedelta(hours=24) if period=='last_24_hours' else midnight).timestamp()
            end_at=midnight.timestamp() if period=='yesterday' else now.timestamp()
        if history_scope is not None:
            start_at,end_at=history_scope['startAt'],history_scope['endAt']; period=history_scope['period']
        date_filtered=start_at is not None
        available=[]; unknown_dates=sum(r.get('recordedAt') is None for r in recordings.values())
        for seg,vector in self.db.segments(self.embedding.signature):
            r=recordings.get(seg['recordingId'])
            if not r or r['status']!='ready': continue
            if date_filtered and (r.get('recordedAt') is None or r['recordedAt']+seg['end']<=start_at or r['recordedAt']+seg['start']>=end_at): continue
            available.append((seg,vector))
        scope_info=dict(recordingCount=len(recordings),indexedSegmentCount=len(available),unknownDateRecordings=unknown_dates,
                        period=period,startAt=start_at,endAt=end_at,cameraId=camera_id,coverage='只查询已导入且完成当前模型索引的录像，不代表摄像头全天覆盖；采集日期未知的录像不参与日期过滤查询。')
        if not available:
            notify('video_search_empty',{})
            return dict(status='no_indexed_recordings',videos=[],scope=scope_info,reason='当前范围没有可检索录像，请导入录像或完成索引')
        notify('video_embedding_started',{})
        q=await self.embedding.embed(text=query)
        scored=[]
        for seg,vector in available:
            if len(q)!=len(vector): raise ProviderError('向量维度不一致，请重新建索引')
            scored.append((sum(a*b for a,b in zip(q,vector)),seg))
        ranked=sorted(scored,key=lambda x:x[0],reverse=True)[:limit]
        notify('video_candidates_found',{'total':len(ranked)})
        completed=0
        async def verify(score,seg):
            nonlocal completed
            failure=False
            r=recordings[seg['recordingId']]
            async with self.verify_gate:
                notify('video_verification_started',{'completed':completed,'total':len(ranked)})
                try: judgment=await self.vision.verify(Path(seg['path']),query,seg['end']-seg['start'])
                except Exception as error:
                    failure=True
                    judgment=dict(verdict='uncertain',summary='候选录像复核未完成',eventTime=None,events=[],
                        limitation=str(error) if isinstance(error,(ValueError,ProviderError)) else '视频理解服务暂不可用')
            completed+=1
            notify('video_verification_progress',{'completed':completed,'total':len(ranked)})
            offset=seg['start']+judgment['eventTime'] if judgment.get('eventTime') is not None else seg['start']
            # Reject answers whose estimated event lies outside the user's requested date window.
            if date_filtered and judgment['verdict']=='matched' and not start_at<=r['recordedAt']+offset<end_at:
                judgment.update(verdict='not_matched',eventTime=None,limitation='该动作时间在本次查询范围之外'); offset=seg['start']
            return dict(id=seg['id'],recordingId=r['id'],cameraId=r['cameraId'],title=r['title'],
                playbackUrl=f"/api/recordings/{r['id']}/video",segmentStart=seg['start'],segmentEnd=seg['end'],
                seekSeconds=offset,recordedAt=r.get('recordedAt'),sourceType=r['sourceType'],
                verificationStatus='failed' if failure else 'completed',
                similarity=round(score,5),verdict=judgment['verdict'],summary=judgment['summary'],
                limitation=judgment.get('limitation',''),events=[e|{'start':e['start']+seg['start'],'end':e['end']+seg['start']} for e in judgment.get('events',[])],
                verifiedBy=self.vision.model,inputKind='video_url',samplingFPS=2,timestampEstimate=True)
        videos=await asyncio.gather(*(verify(score,seg) for score,seg in ranked))
        # Avoid duplicate cards for the same action found in overlapping windows.
        unique=[]
        for v in videos:
            if any(u['recordingId']==v['recordingId'] and u['verdict']==v['verdict']=='matched' and abs(u['seekSeconds']-v['seekSeconds'])<5 for u in unique): continue
            unique.append(v)
        notify('video_search_completed',{'completed':len(ranked),'total':len(ranked)})
        return dict(status='completed',videos=unique,scope=scope_info,candidateCount=len(ranked),
                    embeddingModel=self.embedding.model,verificationModel=self.vision.model,
                    reason='相似度只用于候选排序，不是事件概率；matched 为模型视频复核结果，时间点是估计值，请播放原片核验。')

    async def shutdown(self):
        tasks=list(self.jobs.values())
        for t in tasks: t.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
