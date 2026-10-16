"""Deterministic multimodal retrieval with durable, asynchronous verification.

Media belongs to the authenticated service/team, as in the existing recording
API. Query images and search jobs additionally belong to a proved installation.
There is deliberately no result cache: every new search rechecks SQL scope.
"""
from __future__ import annotations
import asyncio, hashlib, io, json, time, uuid
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from PIL import Image, ImageOps, UnidentifiedImageError
from fastapi import Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from ..history import HistoryFilter, resolve_filter
from ..camera.sources import official_mode, registered_device_ids, visible_recording, REAL_SOURCES
from .providers import ProviderError
from ..ops import private_content


class SearchInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str | None = Field(default=None, max_length=1000)
    image_ref: str | None = Field(default=None, pattern=r'^query-image-[0-9a-f]{32}$')
    camera_ids: list[str] = Field(default_factory=list, max_length=100)
    time_range: HistoryFilter = Field(default_factory=lambda: HistoryFilter(period='all'))
    timezone: str = Field(default='Asia/Shanghai', max_length=100)
    limit: int = Field(default=10, ge=1, le=10)
    verify_limit: int = Field(default=3, ge=1, le=5)

    @field_validator('timezone')
    @classmethod
    def valid_zone(cls, value):
        try: ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError): raise ValueError('时区无效')
        return value

    @model_validator(mode='after')
    def valid_query(self):
        self.text = self.text.strip() if self.text else None
        if not self.text and not self.image_ref: raise ValueError('请填写文字或添加参考图片')
        self.camera_ids = sorted(set(self.camera_ids))
        return self


class VideoSearchService:
    def __init__(self, service):
        self.service, self.store = service, service.store
        self.jobs = {}
        self.query_gate = asyncio.Semaphore(2)
        self.recall_gate = asyncio.Semaphore(1)
        with self.store.transaction():
            self.store.db.execute('''CREATE TABLE IF NOT EXISTS video_query_images
                (id TEXT PRIMARY KEY,owner TEXT NOT NULL,digest TEXT NOT NULL,data BLOB NOT NULL,UNIQUE(owner,digest))''')
            self.store.db.execute('''CREATE TABLE IF NOT EXISTS video_search_jobs
                (id TEXT PRIMARY KEY,owner TEXT NOT NULL,payload TEXT NOT NULL)''')

    def upload_image(self, owner, raw):
        if not owner: raise ValueError('参考图片需要设备身份验证')
        if not 0 < len(raw) <= 5_000_000: raise ValueError('参考图片需为 5 MB 内的 JPEG、PNG 或 WebP')
        try:
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in {'JPEG','PNG','WEBP'} or image.width*image.height > 20_000_000:
                    raise ValueError('图片格式不支持或像素超过 2000 万')
                image.load()
                normalized = ImageOps.exif_transpose(image).convert('RGB')
                normalized.thumbnail((1600,1600))
                output = io.BytesIO(); normalized.save(output, format='JPEG', quality=90)
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
            raise ValueError('参考图片无法读取') from error
        data = output.getvalue(); digest = hashlib.sha256(data).hexdigest()
        with self.store.transaction():
            row = self.store.db.execute('SELECT id FROM video_query_images WHERE owner=? AND digest=?', (owner,digest)).fetchone()
            key = row[0] if row else 'query-image-'+uuid.uuid4().hex
            if not row: self.store.db.execute('INSERT INTO video_query_images VALUES (?,?,?,?)', (key,owner,digest,data))
        return dict(id=key, image_ref=key, url=f'/api/video-search-images/{key}', width=normalized.width, height=normalized.height)

    def image(self, key, owner):
        with self.store.lock:
            row = self.store.db.execute('SELECT data FROM video_query_images WHERE id=? AND owner=?', (key,owner)).fetchone()
        if not row: raise KeyError(key)
        return row[0]

    def image_path(self, key, owner):
        raw = self.image(key, owner)  # Authorize before any disk access.
        folder = self.service.root/'query-images'; folder.mkdir(exist_ok=True)
        path = folder/(hashlib.sha256(raw).hexdigest()+'.jpg')
        if not path.exists(): path.write_bytes(raw)
        return path

    def _save(self, job):
        with self.store.transaction():
            self.store.db.execute('INSERT INTO video_search_jobs VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                (job['id'], job['owner'], json.dumps(job,ensure_ascii=False)))

    def _read(self, key, owner):
        with self.store.lock:
            row = self.store.db.execute('SELECT payload FROM video_search_jobs WHERE id=? AND owner=?', (key,owner)).fetchone()
        if not row: raise KeyError(key)
        return json.loads(row[0])

    def get(self, key, owner):
        job = self._read(key,owner)
        values = []
        for item in job['videos']:
            try: self.service.accessible(item['recordingId'])
            except KeyError: continue
            values.append(item)
        result = {k:v for k,v in job.items() if k != 'owner'}
        result['videos'] = values
        allowed={v['recordingId'] for v in values}
        result['candidateWindows']=[v for v in job.get('candidateWindows',[]) if v['recordingId'] in allowed]
        result['indexChanged'] = job.get('generation') != self.service.index_db.generation
        result['removedCandidates'] = len(job['videos'])-len(values)
        return result

    def recover(self):
        with self.store.lock:
            rows = self.store.db.execute("SELECT payload FROM video_search_jobs WHERE json_extract(payload,'$.status') IN ('searching','verifying')").fetchall()
        for row in rows:
            job = json.loads(row[0]); job.update(status='interrupted',reason='服务重启中断检索，请重新检索；已有候选仍可播放')
            for item in job['videos']:
                if item['verificationStatus']=='verifying': item.update(verificationStatus='failed',verdict='verification_failed',summary='复核被中断')
            self._save(job)

    def start(self, request: SearchInput, owner):
        if not self.service.v2_enabled: raise ValueError('当前为旧版索引，请启用并建立 v2 索引后使用图文检索')
        if not owner: raise ValueError('检索需要设备身份验证')
        if len(self.jobs)>=6 or len(self._owner_jobs(owner))>=2:
            raise ValueError('检索请求较多，请等待当前查询完成')
        if request.image_ref: self.image(request.image_ref, owner)
        selected = set(request.camera_ids) if request.camera_ids else None
        if official_mode(self.service):
            allowed = registered_device_ids(self.store)
            if selected and not selected <= allowed: raise KeyError('camera')
        else:
            allowed = {r['cameraId'] for r in self.service.db.recordings()}
            if selected and not selected <= allowed: raise ValueError('所选摄像头还没有导入录像')
        scope = resolve_filter(request.time_range.model_dump(), timezone=request.timezone)
        scope.update(cameraIds=sorted(selected if selected is not None else allowed),
            coverage='仅覆盖当前服务已入库且完成索引的录像；未知拍摄日期只参加全部日期检索。')
        job = dict(id='search-'+uuid.uuid4().hex, owner=owner, status='searching', query=request.model_dump(),
            scope=scope, createdAt=time.time(), videos=[], reason='正在检索相关片段',
            generation=self.service.index_db.generation, querySignature=self.service.embedding.query_signature,
            indexSignature=self.service.index_signature, timings={}, candidateCount=0, verifiedCount=0)
        self._save(job)
        task = asyncio.create_task(self._execute(job)); self.jobs[job['id']] = task
        task.add_done_callback(lambda _: self.jobs.pop(job['id'],None))
        return self.get(job['id'],owner)

    def _owner_jobs(self, owner):
        with self.store.lock:
            ids = [r[0] for r in self.store.db.execute('SELECT id FROM video_search_jobs WHERE owner=?', (owner,)).fetchall()]
        return [key for key in ids if key in self.jobs]

    @private_content
    async def _execute(self, job):
        began = time.monotonic(); request = SearchInput.model_validate(job['query'])
        try:
            async with self.query_gate:
                job['timings']['queueMs'] = round((time.monotonic()-began)*1000,2)
                image = self.image_path(request.image_ref,job['owner']) if request.image_ref else None
                official = official_mode(self.service)
                cameras = set(job['scope']['cameraIds'])
                if official: cameras &= registered_device_ids(self.store)
                records = [r for r in self.service.db.recordings() if r['cameraId'] in cameras and (not official or visible_recording(r,cameras))]
                job['scope'].update(recordingCount=len(records),unknownDateRecordings=sum(r.get('recordedAt') is None for r in records))
                if not records:
                    job.update(status='no_recordings',reason='当前摄像头范围还没有已导入录像'); self._save(job); return
                start,end = job['scope']['startAt'],job['scope']['endAt']
                where,params = self.service.index_db.where(job['indexSignature'],cameras,start,end,REAL_SOURCES|{'uploaded'} if official else None)
                with self.store.lock:
                    count = self.store.db.execute('SELECT count(*) FROM retrieval_clips c JOIN retrieval_recordings r ON r.id=c.recording_id WHERE '+where,params).fetchone()[0]
                if not count:
                    job.update(status='no_indexed_recordings',reason='所选日期内没有完成当前版本索引的录像；日期未知的录像仅在全部日期中检索')
                    self._save(job); return
                step = time.monotonic()
                q = await self.service.embedding.embed_v2(text=request.text,image=image)
                job['timings']['embeddingMs'] = round((time.monotonic()-step)*1000,2)
                async with self.recall_gate:
                    for attempt in range(2):
                        generation = self.service.index_db.generation
                        work=asyncio.create_task(asyncio.to_thread(self.service.index_db.recall,q,job['indexSignature'],cameras=cameras,
                            start=start,end=end,sources=REAL_SOURCES|{'uploaded'} if official else None,limit=request.limit))
                        try: hits,metrics=await asyncio.shield(work)
                        except asyncio.CancelledError:
                            # A Python worker cannot be forcibly stopped; let it
                            # release SQLite before shutdown closes the database.
                            await work; raise
                        if self.service.index_db.generation==generation: break
                    else: raise ValueError('索引正在更新，请稍后重新检索')
                job.update(generation=generation,metrics=metrics)
                job['timings']['recallMs'] = metrics['recallMs']
                for rank, hit in enumerate(hits,1):
                    clip=hit['clip']; r=clip['recording']
                    try: self.service.accessible(r['id'])
                    except KeyError: continue
                    low,high=clip['start'],clip['end']
                    if start is not None:
                        low=max(low,start-r['recordedAt']); high=min(high,end-r['recordedAt'])
                    seek=hit['frame']['offset'] if hit['frame'] else low
                    seek=min(max(seek,low),high-.001)
                    job['videos'].append(dict(id=clip['id'],clipId=clip['id'],recordingId=r['id'],cameraId=r['cameraId'],title=r['title'],
                        playbackUrl=f"/api/recordings/{r['id']}/video",thumbnailUrl=f"/api/video-search/{job['id']}/thumbnails/{clip['id']}",
                        segmentStart=clip['start'],segmentEnd=clip['end'],scopeStart=low,scopeEnd=high,seekSeconds=seek,recordedAt=r.get('recordedAt'),
                        sourceType=r['sourceType'],verificationStatus='candidate',verdict='candidate',summary='相关候选，尚未经视频核验',
                        limitation='相关排序不是发生证明；请播放核对。',events=[],rank=rank,ranking=hit['ranks'],intervals=hit['intervals'],
                        referenceImageUsed=bool(image),timestampEstimate=True))
            job.update(status='verifying' if job['videos'] else 'no_candidates',candidateCount=len(job['videos']),
                reason='找到相关片段，正在核对前几个候选' if job['videos'] else '当前范围没有可用候选')
            job['timings']['firstCandidatesMs']=round((time.monotonic()-began)*1000,2)
            job['candidateWindows']=[{k:item[k] for k in ('recordingId','clipId','segmentStart','segmentEnd','rank')} for item in job['videos']]
            self._save(job)  # Publish before waiting for even one verification call.
            await asyncio.sleep(0)
            if not job['videos']: return
            by_id={hit['clip']['id']:hit for hit in hits}
            await asyncio.gather(*(self._verify(job,item,by_id[item['id']],image) for item in job['videos'][:request.verify_limit]))
            # Same observed event in overlapping windows becomes one card; distant
            # events in the same recording remain separate.
            unique=[]
            for item in job['videos']:
                duplicate=next((v for v in unique if v['recordingId']==item['recordingId'] and v['verdict']==item['verdict']=='matched'
                    and abs(v['seekSeconds']-item['seekSeconds'])<5),None)
                if duplicate: duplicate['intervals'].extend(item['intervals'])
                else: unique.append(item)
            order={'matched':0,'uncertain':1,'candidate':2,'verification_failed':3,'not_matched':4}
            job['videos']=sorted(unique,key=lambda v:(order[v['verdict']],v['rank']))
            job.update(status='completed',reason='复核只覆盖标记的片段；其他仍为候选。外观相似不证明身份，未找到不代表从未发生。')
        except asyncio.CancelledError:
            job.update(status='interrupted',reason='检索已中断，请重新提交')
            raise
        except Exception as error:
            job.update(status='failed',reason=str(error) if isinstance(error,(ProviderError,ValueError)) else '检索服务暂不可用，请重试')
        finally:
            job['timings']['totalMs']=round((time.monotonic()-began)*1000,2)
            self._save(job)

    async def _verify(self, job, item, hit, image):
        async with self.service.verify_gate:
            item.update(verificationStatus='verifying',summary='正在核对原录像'); self._save(job)
            try:
                self.service.accessible(item['recordingId'])
                duration=item['segmentEnd']-item['segmentStart']
                kwargs={'reference_image':image} if image else {}
                media=self.media_path(hit['clip']['path'],item['recordingId'])
                judgment=await self.service.vision.verify(media,job['query']['text'] or '',duration,**kwargs)
                offset=judgment.get('eventTime')
                if offset is not None and (not isinstance(offset,(float,int)) or not 0<=offset<=duration):
                    raise ValueError('复核时间超出候选片段')
                if judgment['verdict']=='matched':
                    if offset is None: raise ValueError('复核匹配缺少事件时间')
                    position=item['segmentStart']+offset
                    if not item['scopeStart']<=position<item['scopeEnd']:
                        judgment.update(verdict='not_matched',summary='所见事件在所选时间范围之外',eventTime=None,events=[])
                    else: item['seekSeconds']=position
                events=[]
                for event in judgment.get('events',[]):
                    a,b=event['start']+item['segmentStart'],event['end']+item['segmentStart']
                    if item['scopeStart']<=a<=b<=item['scopeEnd']: events.append(event|{'start':a,'end':b})
                item.update(verificationStatus='completed',verdict=judgment['verdict'],summary=judgment['summary'],
                    limitation=judgment.get('limitation',''),events=events,verifiedBy=self.service.vision.model)
            except Exception as error:
                # Transport/parser/provider errors never masquerade as absence.
                item.update(verificationStatus='failed',verdict='verification_failed',summary='视频复核失败，可重新检索或播放核对',
                    limitation='模型或网络未完成核验，不能据此判断没有发生。',events=[],verificationErrorCode=getattr(error,'code','verification_failed'))
            job['verifiedCount']+=1; self._save(job)

    def thumbnail(self, key, clip_id, owner):
        job=self.get(key,owner)
        item=next((v for v in job['videos'] if v['id']==clip_id),None)
        if not item: raise KeyError(clip_id)
        r=self.service.accessible(item['recordingId'])
        with self.store.lock:
            rows=self.store.db.execute('''SELECT thumbnail,offset_ms FROM retrieval_embeddings
                WHERE clip_id=? AND signature=? AND kind='frame' ORDER BY abs(offset_ms-?)''',
                (clip_id,job['indexSignature'],item['seekSeconds']*1000)).fetchall()
        for path, offset in rows:
            if item['scopeStart']<=offset/1000<item['scopeEnd']:
                return self.media_path(path,r['id'])
        # No frame inside a narrow time filter: do not show an out-of-range image.
        raise KeyError(clip_id)

    def media_path(self, reference, recording_id):
        resolved=(self.service.root/reference).resolve()
        root=(self.service.root/recording_id).resolve()
        if root.parent!=self.service.root or not resolved.is_relative_to(root) or not resolved.is_file(): raise KeyError(recording_id)
        return resolved

    async def shutdown(self):
        tasks=list(self.jobs.values())
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)


def install_search_routes(app, service, owner):
    from fastapi.responses import FileResponse
    @app.post('/api/video-search-images',status_code=201)
    async def upload(request: Request):
        client=owner(request); data=bytearray()
        async for chunk in request.stream():
            if len(data)+len(chunk)>5_000_000: raise ValueError('参考图片不能超过 5 MB')
            data.extend(chunk)
        return await asyncio.to_thread(service.retrieval.upload_image,client,bytes(data))
    @app.get('/api/video-search-images/{image_id}')
    async def read_image(image_id: str,request: Request):
        return Response(service.retrieval.image(image_id,owner(request)),media_type='image/jpeg',headers={'Cache-Control':'private, no-store'})
    @app.post('/api/video-search',status_code=202)
    async def search(body: SearchInput,request: Request):
        return service.retrieval.start(body,owner(request))
    @app.get('/api/video-search/{search_id}')
    async def status(search_id: str,request: Request):
        return service.retrieval.get(search_id,owner(request))
    @app.get('/api/video-search/{search_id}/thumbnails/{clip_id}')
    async def thumbnail(search_id: str,clip_id: str,request: Request):
        return FileResponse(service.retrieval.thumbnail(search_id,clip_id,owner(request)),media_type='image/jpeg',headers={'Cache-Control':'private, no-store'})
    @app.delete('/api/recordings/{recording_id}')
    async def delete(recording_id: str,request: Request):
        owner(request)
        return await service.delete_recording(recording_id)
