"""Scheduled camera observations share capture leases, visual budgets and APNs gates."""
import asyncio
import json
import time
import uuid
from pydantic import BaseModel, ConfigDict, Field
from .sources import REAL_SOURCES


class WatchOptions(BaseModel):
    model_config=ConfigDict(extra='forbid')
    enabled: bool = False
    intervalSeconds: int = Field(default=1800,ge=300,le=86400)


class CameraWatch:
    def __init__(self, store, captures, visual, proactive):
        self.store,self.captures,self.visual,self.proactive=store,captures,visual,proactive
        self.lock=asyncio.Lock()
        proactive.watch=self
        with store.transaction():
            store.db.executescript('''
                CREATE TABLE IF NOT EXISTS camera_watches (camera TEXT PRIMARY KEY, due REAL NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS camera_observations (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            ''')

    def get(self, camera):
        with self.store.lock: row=self.store.db.execute('SELECT payload FROM camera_watches WHERE camera=?',(camera,)).fetchone()
        return json.loads(row[0]) if row else dict(cameraId=camera,enabled=False,intervalSeconds=1800,revision=0,status='disabled',reason='尚未开启定时观察')

    async def snapshot(self):
        devices=await self.captures.cameras.manifests()
        return [self.get(d.id) | dict(name=d.name,connection=d.connection,visualUsage=self.visual.usage(d.id)) for d in devices]

    async def configure(self, camera, options):
        devices={d.id for d in await self.captures.cameras.manifests()}
        if camera not in devices: raise ValueError('请先连接摄像头')
        with self.store.transaction():
            old=self.get(camera)
            value=old | options.model_dump() | dict(revision=old['revision']+1,status='waiting' if options.enabled else 'disabled',reason='等待下次观察；需要在线采集端' if options.enabled else '定时观察已暂停')
            self.store.db.execute('INSERT OR REPLACE INTO camera_watches VALUES (?,?,?)',(camera,time.time(),json.dumps(value,ensure_ascii=False)))
        return await self.snapshot()

    def observation(self, key):
        with self.store.lock: row=self.store.db.execute('SELECT payload FROM camera_observations WHERE id=?',(key,)).fetchone()
        return json.loads(row[0]) if row else None

    def sources(self, key):
        item=self.observation(key)
        if not item: return []
        receipt=item['capture']
        return [dict(id=key,type='task_state',name=item['name'],result=item['status'],revision=item['revision'],reason=item['reason']),
                dict(id='evidence:'+key,type='camera_evidence',evidenceId=key,cameraId=item['cameraId'],
                     observedAt=item['observedAt'],sourceType=receipt['sourceType'],imageUrl=receipt['imageUrl'],
                     visualReview=item['review'],reason='定时取样',limitation='一张离散取样；客户端取样时间不是设备拍摄时间，不能证明连续状态或完整动作')]

    async def step(self, now=None):
        now=time.time() if now is None else now
        async with self.lock:
            with self.store.transaction():
                row=self.store.db.execute("SELECT camera FROM camera_watches WHERE due<=? AND json_extract(payload,'$.enabled')=1 ORDER BY due LIMIT 1",(now,)).fetchone()
                if not row: return False
                camera=row[0]; config=self.get(camera)
                self.store.db.execute('UPDATE camera_watches SET due=? WHERE camera=?',(now+config['intervalSeconds'],camera))
            key='observation-'+uuid.uuid4().hex
            # Never take over a task's camera lease; capture() checks occupancy,
            # live session freshness and the frame's challenge/sequence.
            try: receipt=await self.captures.capture(camera,purpose='用户开启的定时观察')
            except (ValueError,KeyError): receipt=dict(status='failed',reason='摄像头正被任务占用或暂不可用，未接管设备')
            except asyncio.CancelledError: raise
            except Exception: receipt=dict(status='failed',reason='本次采集未完成，等待下次观察')
            result=dict(status='unavailable',reason=receipt.get('reason','画面暂不可用'))
            if receipt['status']=='completed':
                if receipt.get('sourceType') in REAL_SOURCES:
                    observed=receipt.get('capturedAt') or receipt.get('sampledAt')
                    if observed is None or not 0<=time.time()-observed<=300:
                        result=dict(status='unavailable',reason='画面时间无法确认或已过期，本次不作为新动态')
                    else:
                        result=await self.visual.review(camera,key,[(receipt['mediaId'],observed)])
                else: result=dict(status='unavailable',reason='定时观察仅接受真实采集来源，测试图片不作为家庭现场')
            device=next((d for d in await self.captures.cameras.manifests() if d.id==camera),None)
            with self.store.transaction():
                current=self.get(camera)
                if current['revision']!=config['revision'] or not current['enabled']: return True
                status=result['status']; reason=result.get('reason') or result.get('review',{}).get('visible','已完成本次取样核验')
                current.update(status=status,reason=reason,lastAttemptAt=now)
                self.store.db.execute('UPDATE camera_watches SET payload=? WHERE camera=?',(json.dumps(current,ensure_ascii=False),camera))
                if status!='completed': return True
                observed=receipt.get('capturedAt') or receipt.get('sampledAt')
                if observed is None or not 0<=time.time()-observed<=300: return True
                item=dict(id=key,cameraId=camera,name=device.name if device else '摄像头',capture=receipt,
                          observedAt=observed,review=result,status=status,reason=reason,revision=config['revision'])
                self.store.db.execute('INSERT INTO camera_observations VALUES (?,?)',(key,json.dumps(item,ensure_ascii=False)))
                evidence=dict(id=key,skillId='',cameraId=camera,capturedAt=observed,relation='unknown',reason=reason,
                              imageUrl=receipt['imageUrl'],revision=0,sourceType=receipt['sourceType'],mediaStatus='saved',
                              frameId=receipt['frameId'],timestampMeaning=receipt['timestampMeaning'],reviewStatus='completed')
                self.store.db.execute('INSERT INTO evidence VALUES (?,?,?,?)',(key,'',observed,json.dumps(evidence,ensure_ascii=False)))
                for (client,) in self.store.db.execute('SELECT id FROM personal_profiles').fetchall():
                    if self.proactive.personal.profile(client)['preferences']['enabled']:
                        self.proactive.enqueue(client,key,'camera_observation',item['name']+' 的定时观察',reason,time.time())
            return True

    async def run(self):
        while True:
            try: await self.step()
            except asyncio.CancelledError: raise
            except Exception: pass  # Per-camera next due is persisted; retry on the next interval.
            await asyncio.sleep(2)
