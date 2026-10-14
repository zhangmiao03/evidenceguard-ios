"""Native SDK event relay. Read-only imports never grant camera control or arm a Skill."""
from __future__ import annotations
import asyncio
import base64
import hashlib
import json
import time
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class SDKEvent(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    eventId: str = Field(min_length=1,max_length=300)
    deviceSn: str = Field(min_length=1,max_length=100)
    model: Literal['T8171','T8214']
    deviceName: str = Field(min_length=1,max_length=100)
    startMs: int = Field(gt=0)
    endMs: int = Field(gt=0)
    detectionType: str = Field(default='unknown',max_length=64)
    hasVideo: bool = False
    imageBase64: str | None = Field(default=None,max_length=7_000_000)
    imageSource: Literal['event_thumbnail'] = 'event_thumbnail'

    @model_validator(mode='after')
    def timestamps(self):
        if self.endMs < self.startMs or self.endMs > (time.time()+300)*1000:
            raise ValueError('事件时间无效，请核对设备时钟')
        return self


class SDKBatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    events: list[SDKEvent] = Field(min_length=1,max_length=10)
    reviewRequested: bool = False


class SDKDevice(BaseModel):
    model_config = ConfigDict(extra='forbid')
    deviceSn: str = Field(min_length=1,max_length=100)
    model: Literal['T8171','T8214']
    deviceName: str = Field(min_length=1,max_length=100)


class SDKDevices(BaseModel):
    model_config = ConfigDict(extra='forbid')
    devices: list[SDKDevice] = Field(max_length=50)


class SDKIngest:
    def __init__(self, store, visual, personal):
        self.store, self.visual, self.personal = store, visual, personal
        self.lock = asyncio.Lock()
        with store.transaction():
            store.db.executescript('''
                CREATE TABLE IF NOT EXISTS sdk_devices (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sdk_events (
                    id TEXT PRIMARY KEY, camera TEXT NOT NULL, episode TEXT NOT NULL,
                    received REAL NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sdk_episodes (
                    id TEXT PRIMARY KEY, camera TEXT NOT NULL, due REAL NOT NULL,
                    status TEXT NOT NULL, payload TEXT NOT NULL);
            ''')
            store.db.execute("UPDATE sdk_episodes SET status='pending' WHERE status='running'")
            # Preserve SDK imports from earlier builds without creating placeholder devices.
            for (payload,) in store.db.execute('SELECT payload FROM sdk_events').fetchall():
                event=json.loads(payload); meta=event['metadata']
                value=dict(id=event['cameraId'],model=meta['model'],name=meta['deviceName'],registeredAt=event['receivedAt'])
                store.db.execute('INSERT OR IGNORE INTO sdk_devices VALUES (?,?)',(event['cameraId'],json.dumps(value,ensure_ascii=False)))

    @staticmethod
    def camera_id(sn): return 'sdk-'+hashlib.sha256(sn.encode()).hexdigest()[:20]

    def register_devices(self, batch):
        with self.store.transaction():
            for device in batch.devices:
                key=self.camera_id(device.deviceSn)
                # Discovery reports identity only, never live capture capability or credentials.
                value=dict(id=key,model=device.model,name=device.deviceName,registeredAt=time.time())
                self.store.db.execute('INSERT INTO sdk_devices VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                                      (key,json.dumps(value,ensure_ascii=False)))
        return dict(cameraIds=[self.camera_id(d.deviceSn) for d in batch.devices])

    def devices(self):
        with self.store.lock:
            rows=self.store.db.execute('SELECT payload FROM sdk_devices ORDER BY id').fetchall()
        return [json.loads(row[0]) for row in rows]

    @staticmethod
    def image(value):
        if not value: return None
        try: raw=base64.b64decode(value,validate=True)
        except (ValueError,TypeError): raise ValueError('图片必须是有效的 Base64 内容，不接受本地路径')
        if not raw or len(raw)>5*1024*1024: raise ValueError('事件图片上限为5MB')
        mime = 'image/jpeg' if raw.startswith(b'\xff\xd8\xff') and raw.endswith(b'\xff\xd9') else 'image/png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else None
        if not mime: raise ValueError('仅接收事件 JPEG/PNG 图片')
        return raw,mime

    def accept(self, batch, client, now=None):
        now = time.time() if now is None else now
        # Validate every image first: a rejected batch must not be partially saved.
        decoded=[self.image(e.imageBase64) for e in batch.events]
        receipts=[]
        with self.store.transaction():
            for event, image in zip(batch.events,decoded):
                camera=self.camera_id(event.deviceSn)
                self.register_devices(SDKDevices(devices=[SDKDevice(deviceSn=event.deviceSn,model=event.model,deviceName=event.deviceName)]))
                key='sdk-event-'+hashlib.sha256((event.deviceSn+'\0'+event.eventId).encode()).hexdigest()
                metadata=event.model_dump(exclude={'imageBase64'})
                row=self.store.db.execute('SELECT payload FROM sdk_events WHERE id=?',(key,)).fetchone()
                old=json.loads(row[0]) if row else None
                if old and old['metadata']!=metadata: raise ValueError('同一官方事件的元数据发生冲突，未覆盖已有证据')
                digest=hashlib.sha256(image[0]).hexdigest() if image else None
                if old and old.get('imageDigest') and digest and old['imageDigest']!=digest:
                    raise ValueError('同一事件图片发生冲突，未覆盖已有证据')
                changed=old is None or (image is not None and not old.get('imageDigest'))
                episode='sdk-episode-'+hashlib.sha256(f'{camera}:{event.detectionType}:{event.startMs//10000}'.encode()).hexdigest()
                data=old or dict(id=key,cameraId=camera,metadata=metadata,sourceType='official_sdk',
                                 receivedAt=now,receivedBy=client,episodeId=episode,imageUrl=None,imageDigest=None)
                if changed:
                    if image:
                        media=self.store.save_media(dict(device_id=camera,frame_id=key,source_type='official_sdk',
                                                         captured_at=None,event_at=event.startMs/1000,received_at=now),*image)
                        data.update(imageUrl=media['imageUrl'],imageDigest=digest)
                    self.store.db.execute('INSERT INTO sdk_events VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                                          (key,camera,episode,now,json.dumps(data,ensure_ascii=False)))
                    evidence=dict(id=key,skillId='',cameraId=camera,capturedAt=event.startMs/1000,
                                  relation='unknown',reason='官方事件已保存；尚未核验画面，不代表实时现场。',
                                  imageUrl=data['imageUrl'],revision=0,sourceType='official_sdk',
                                  mediaStatus='saved' if data['imageUrl'] else 'unavailable',frameId=key,
                                  timestampMeaning='device_event',deviceName=event.deviceName,
                                  detectionType=event.detectionType,reviewStatus='saved')
                    self.store.db.execute('INSERT INTO evidence VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                                          (key,'',event.startMs/1000,json.dumps(evidence,ensure_ascii=False)))
                # Explicit review import is read-only; no Skill approval is inferred.
                ep=self.episode(episode)
                if batch.reviewRequested and (not ep or changed):
                    payload=(ep or {}) | dict(id=episode,cameraId=camera,kind=event.detectionType,deviceName=event.deviceName,
                                               updatedAt=now,reason='等待合并事件图片后核验',revision=(ep or {}).get('revision',0)+1)
                    # Explicit imports may be historical. Known scene event types
                    # are the code-side prefilter; unsupported codes remain records.
                    status='pending' if event.detectionType in {'package_put','package_take','human','motion','vehicle','pet','ring'} else 'filtered'
                    if status=='filtered': payload['reason']='事件类型尚未纳入自动核验，原始记录已保存'
                    self.store.db.execute("INSERT INTO sdk_episodes VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,due=excluded.due,payload=excluded.payload",
                                          (episode,camera,now+10,status,json.dumps(payload,ensure_ascii=False)))
                receipts.append(dict(id=key,status='saved' if changed else 'duplicate',imageSaved=bool(data['imageUrl'])))
        return dict(receipts=receipts,sourceType='official_sdk',continuousCoverage=False)

    def episode(self, key):
        with self.store.lock:
            row=self.store.db.execute('SELECT payload,status FROM sdk_episodes WHERE id=?',(key,)).fetchone()
        return json.loads(row[0]) | {'status':row[1]} if row else None

    def events(self, episode=None, camera=None):
        with self.store.lock:
            clauses=[]; parameters=[]
            if episode: clauses.append('episode=?'); parameters.append(episode)
            if camera: clauses.append('camera=?'); parameters.append(camera)
            rows=self.store.db.execute('SELECT payload FROM sdk_events '+('WHERE '+' AND '.join(clauses)+' ' if clauses else '')+"ORDER BY json_extract(payload,'$.metadata.startMs') DESC LIMIT 101",parameters).fetchall()
        return [json.loads(r[0]) for r in rows]

    def timeline(self, camera=None):
        values=self.events(camera=camera)
        items=[]
        for event in values[:100]:
            meta=event['metadata']; episode=self.episode(event['episodeId'])
            items.append(dict(id=event['id'],cameraId=event['cameraId'],deviceName=meta['deviceName'],
                              startMs=meta['startMs'],endMs=meta['endMs'],detectionType=meta['detectionType'],
                              hasVideo=meta['hasVideo'],imageUrl=event['imageUrl'],
                              reviewStatus='completed' if episode and event['id'] in episode.get('reviewedEvidenceIds',[]) else episode['status'] if episode and episode['status']!='completed' else 'saved',
                              reason=(episode or {}).get('reason','事件已保存'),sourceType='official_sdk'))
        return dict(events=sorted(items,key=lambda e:e['startMs'],reverse=True),truncated=len(values)>100,continuousCoverage=False)

    def sources(self, key):
        ep=self.episode(key)
        if not ep: return []
        sources=[dict(id=key,type='task_state',name=ep['deviceName'],result=ep['status'],revision=ep['revision'],
                      reason=ep['reason'],review=ep.get('review'),limitation='已导入的事件，不等于持续守护')]
        for e in self.events(key):
            if e['id'] not in ep.get('reviewedEvidenceIds',[]): continue
            sources.append(dict(id='evidence:'+e['id'],type='camera_evidence',evidenceId=e['id'],cameraId=e['cameraId'],
                                observedAt=e['metadata']['startMs']/1000,sourceType='official_sdk',imageUrl=e['imageUrl'],
                                reason=e['metadata']['detectionType'],visualReview=ep.get('review'),
                                limitation='时间为设备事件时间；缩略图不保证是实时画面，SDK事件类型未代表模型已确认'))
        return sources

    async def step(self, now=None):
        now=time.time() if now is None else now
        async with self.lock:
            with self.store.transaction():
                row=self.store.db.execute("SELECT id FROM sdk_episodes WHERE status='pending' AND due<=? ORDER BY due LIMIT 1",(now,)).fetchone()
                if not row: return False
                ep=self.episode(row[0]); revision=ep['revision']
                ep['attempts']=ep.get('attempts',0)+1
                self.store.db.execute("UPDATE sdk_episodes SET status='running' WHERE id=?",(ep['id'],))
                events=self.events(ep['id'])
            selected=sorted([e for e in events if e['imageUrl']],key=lambda e:e['metadata']['startMs'])
            # First/middle/last bound image cost while retaining event order.
            if len(selected)>3: selected=[selected[0],selected[len(selected)//2],selected[-1]]
            result=await self.visual.review(ep['cameraId'],ep['id'],[(e['imageUrl'].split('/')[-1],e['metadata']['startMs']/1000) for e in selected])
            with self.store.transaction():
                current=self.episode(ep['id'])
                if current['revision']!=revision: return True  # A new image arrived; next job uses it.
                reviewed=[e['id'] for e in selected] if result['status']=='completed' else []
                ep.update(review=result,reviewedEvidenceIds=reviewed,reason=result.get('reason') or '已核验事件缩略图，未据此启用守护或认定拿走动作')
                retry=result['status']=='unavailable' and bool(selected) and self.visual.provider.ready and ep['attempts']<2
                self.store.db.execute('UPDATE sdk_episodes SET status=?,due=?,payload=? WHERE id=?',
                                      ('pending' if retry else result['status'],now+30,json.dumps(ep,ensure_ascii=False),ep['id']))
                for e in events:
                    row=self.store.db.execute('SELECT payload FROM evidence WHERE id=?',(e['id'],)).fetchone()
                    item=json.loads(row[0]); review=result.get('review',{})
                    item['reviewStatus']='completed' if e['id'] in reviewed else result['status'] if result['status']!='completed' else 'saved'
                    item['reason']=((review.get('visible','')+'\n'+review.get('uncertainties','')).strip() or ep['reason']) if e['id'] in reviewed else '事件已保存；本条图片未完成视觉核验。'+result.get('reason','')
                    item['reason']+='\n事件缩略图核验；不代表实时现场或连续录像。'
                    self.store.db.execute('UPDATE evidence SET payload=? WHERE id=?',(json.dumps(item,ensure_ascii=False),e['id']))
                # Historical imports never masquerade as new household events.
                latest=max(e['metadata']['startMs']/1000 for e in events)
                if result['status']=='completed' and 0 <= now-latest <= 300:
                    profiles=self.store.db.execute('SELECT id FROM personal_profiles').fetchall()
                    for (client,) in profiles:
                        if self.personal.profile(client)['preferences']['enabled']:
                            self.personal.engine.enqueue(client,ep['id'],'camera_event',ep['deviceName']+' 有新的事件',ep['reason'],now)
            return True

    def status(self):
        with self.store.lock:
            rows=self.store.db.execute('SELECT id FROM sdk_episodes ORDER BY due DESC LIMIT 20').fetchall()
        return dict(episodes=[self.episode(r[0]) for r in rows],continuousCoverage=False,
                    message='仅分析已导入事件；前台同步暂停或手机锁屏后，不保证持续接收')

    async def run(self):
        while True:
            try: await self.step()
            except asyncio.CancelledError: raise
            except Exception:
                with self.store.transaction():
                    self.store.db.execute("UPDATE sdk_episodes SET status='failed' WHERE status='running'")
            await asyncio.sleep(2)
