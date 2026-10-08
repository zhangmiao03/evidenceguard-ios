from __future__ import annotations
import asyncio, copy, time
from .schemas import SkillRules
from .timing import accumulate
from .harness.scheduler import TaskEnvelope

class ObservationWorker:
    """Deterministic state engine. The current detector is explicitly fixture-marker only."""
    def __init__(self,store,cameras,interval=1.2,camera_service=None,scheduler=None,replay_worker=None):
        self.store,self.cameras,self.interval=store,cameras,interval
        self.camera_service,self.scheduler=camera_service,scheduler
        self.replay_worker=replay_worker
        self.last_error=None
        self.capture_jobs={}
        # Recovery retains episode/position, discards partial confirmations and demands new frames.
        for s in store.skills():
            if s['status']=='active' and not s.get('replay'):
                cp=s.get('evaluation',{}); cp.pop('candidate',None)
                s.update(evaluation=cp,notBefore=time.time(),result='unknown',resultReason='服务恢复，等待新的观察依据')
                store.save_skill(s)
                store.event(s['id'],'observation_recovered',{'episode':cp.get('episode',0)})

    def evaluate(self,skill,cameras,now):
        rules=SkillRules.model_validate(skill.get('rules',{}))
        cp=copy.deepcopy(skill.get('evaluation',{})); candidate=cp.get('candidate',{})
        if now-cp.get('lastSampleAt',-1e20)<rules.sampleIntervalSeconds:return self.store.skill(skill['id']) or skill
        cp['lastSampleAt']=now
        proofs=[]; valid=[]; views=skill.setdefault('viewRevisions',{})
        last_frames=cp.setdefault('lastFrames',{})
        for camera in cameras:
            d=camera['id']; o=camera.get('observation')
            if d not in skill['devices'] or not o: continue
            if o.get('device_id')!=d or o.get('channel_id','main')!='main': continue
            if not camera.get('transport_online') or not (skill.get('notBefore',0)<=o['captured_at']<=now+.5 and now-o['captured_at']<6): continue
            # An older packet cannot roll back the checkpoint, even if it is still within freshness.
            previous=last_frames.get(d,{})
            if o['captured_at'] < previous.get('at',0): continue
            same_time=o['captured_at']==previous.get('at') and o['frame_id']!=previous.get('id')
            if same_time: continue
            last_frames[d]={'at':o['captured_at'],'id':o['frame_id']}
            view=str(o.get('revision','unknown'))
            views.setdefault(d,view)
            p=dict(o); p['relation']='unknown'
            p['reason']='测试目标不可见，保留判断'
            box=o.get('bbox'); roi=skill['regions'][d]
            if views[d]!=view:
                p['reason']='摄像头视角版本已变化，请重新确认区域'
            elif box and 17 in o.get('marker_ids',[]) and o.get('source_type')=='fixture':
                x1,y1,x2,y2=box
                margin=.015
                inside=x1>=roi['x']+margin and y1>=roi['y']+margin and x2<=roi['x']+roi['width']-margin and y2<=roi['y']+roi['height']-margin
                outside=x2<roi['x']-margin or x1>roi['x']+roi['width']+margin or y2<roi['y']-margin or y1>roi['y']+roi['height']+margin
                p['relation']='inside' if inside else 'outside' if outside else 'unknown'
                p['reason']='测试标记与本任务区域比较；边界保留判断'
            proofs.append(p)
            if p['relation']!='unknown': valid.append(p)
        primary=next((p for p in proofs if p['device_id']==skill['target']['cameraId']),None)
        cp['primaryUnclear']=primary is None or primary['relation']=='unknown'
        chosen=None; reason='没有新鲜且清晰的画面，暂不判断'
        if valid:
            if len({p['relation'] for p in valid})>1: reason='两路有效证据冲突，暂不判断'
            elif max(p['captured_at'] for p in valid)-min(p['captured_at'] for p in valid)>2:
                reason='两路画面时间不同步，等待新证据'
            else:
                chosen=sorted(valid,key=lambda p:(p['device_id']!=skill['target']['cameraId'],-p['captured_at']))[0]
                if primary and primary['captured_at']-chosen['captured_at']>2:
                    chosen=None; reason='补充视角落后，不能确认当前状态'
        result='unknown'; alert=skill['alert']; triggered=False
        if chosen:
            key=chosen['device_id']+':'+chosen['relation']+':'+str(chosen.get('revision'))
            if candidate.get('proof')!=chosen['frame_id']:
                candidate=accumulate(candidate,key,chosen['captured_at'],chosen['frame_id'],rules.sampleIntervalSeconds)
            if candidate.get('span',0)>=rules.confirmationSeconds:
                origin='inside' if rules.trigger=='leaves_region' else 'outside'
                relation=chosen['relation']
                if relation==origin:
                    cp.update(armed=True,latched=False,position=relation)
                    result='confirmed'; reason='新证据确认目标在区域内' if relation=='inside' else '新证据确认目标在区域外，等待进入'
                    if alert in {'open','acknowledged'}: alert='resolved'
                elif cp.get('armed'):
                    if not cp.get('latched'):
                        cp['episode']=cp.get('episode',0)+1; alert='open'; triggered=True
                    cp.update(latched=True,position=relation)
                    result='needs_attention'
                    reason='连续观察确认测试目标离开区域' if relation=='outside' else '连续观察确认测试目标进入区域'
                else:
                    cp['position']=relation
                    reason='已观察到目标位置，尚缺少触发前的基线，继续观察'
                if chosen['device_id']!=skill['target']['cameraId']: reason+=' · 补充视角'
            else: reason=f"按 {rules.sampleIntervalSeconds} s 抽样，确认跨度 {candidate.get('span',0):.0f}/{rules.confirmationSeconds} s"
        else:
            candidate={}
        cp['candidate']=candidate
        if result=='unknown': cp.setdefault('unknownSince',now)
        else: cp.pop('unknownSince',None)
        if not cp['primaryUnclear']:
            cp['supplementAttempts']=0
        old_result=skill['result']; old_alert=skill['alert']
        skill.update(evaluation=cp)
        # Evaluation, semantic transition and event writes share one transaction.
        with self.store.transaction():
            current=self.store.skill(skill['id'])
            if not current or current['status']!='active' or current.get('executionEpoch')!=skill.get('executionEpoch'):
                return current or skill
            self.store.save_skill(skill)
            result_skill=self.store.sync_observation(skill['id'],{'task':dict(result=result,reason=reason,alert=alert,evidence=proofs)})
            if triggered:
                self.store.event(skill['id'],'alert_opened',{'episode':cp['episode'],'revision':skill['revision'],'frames':[p['frame_id'] for p in proofs]})
            elif old_alert in {'open','acknowledged'} and alert=='resolved':
                self.store.event(skill['id'],'alert_resolved',{'episode':cp.get('episode',0)})
            if triggered and rules.completion=='once':
                result_skill['status']='completed'; self.store.save_skill(result_skill)
                self.store.event(skill['id'],'skill_completed',{'episode':cp['episode']})
        return result_skill

    async def persist_evidence(self):
        for e in self.store.evidence(limit=100):
            if e.get('mediaStatus')!='pending': continue
            try:
                raw,mime=await self.cameras.frame_bytes(e['cameraId'],e['frameId'])
                media=self.store.save_media(dict(device_id=e['cameraId'],frame_id=e['frameId'],captured_at=e['capturedAt']),raw,mime)
                self.store.attach_evidence_media(e['id'],media)
            except Exception:
                self.store.attach_evidence_media(e['id'])

    def schedule_capture(self,skill,now):
        if not self.camera_service: return
        cp=skill.get('evaluation',{})
        primary=skill['target']['cameraId']
        due=[]
        period=SkillRules.model_validate(skill.get('rules',{})).sampleIntervalSeconds
        if now-cp.get('lastPrimaryRequest',0)>=period:
            due.append((primary,'定期请求当前任务新画面')); cp['lastPrimaryRequest']=now
        if cp.get('primaryUnclear') and cp.get('supplementAttempts',0)<3 and now-cp.get('lastSupplementRequest',0)>=max(period,8):
            due += [(d,'主视角无法确认，请求补证') for d in skill['devices'] if d!=primary]
            if len(skill['devices'])>1:
                cp['lastSupplementRequest']=now; cp['supplementAttempts']=cp.get('supplementAttempts',0)+1
        skill['evaluation']=cp; self.store.save_skill(skill)
        for device,purpose in due:
            key=(skill['id'],device)
            if key in self.capture_jobs: continue
            async def capture(sid=skill['id'],d=device,p=purpose,k=key):
                try: await self.camera_service.capture(d,sid,p)
                except Exception: pass  # CameraService records failures; queue overload is retried on the next budget window.
                finally: self.capture_jobs.pop(k,None)
            self.capture_jobs[key]=asyncio.create_task(capture())

    async def tick(self):
        try:
            lab=await self.cameras.state(); self.last_error=None
            cameras=lab.get('cameras',[])
        except Exception:
            cameras=[]; self.last_error='摄像头数据源不可用'
        skills=self.store.skills()
        active_ids={s['id'] for s in skills if s['status']=='active'}
        for key,job in list(self.capture_jobs.items()):
            if key[0] not in active_ids: job.cancel()
        for skill in skills:
            if skill['status']=='active' and not skill.get('replay'):
                updated=self.evaluate(skill,cameras,time.time())
                if updated['status']=='active': self.schedule_capture(updated,time.time())
        if self.replay_worker: await self.replay_worker.tick()
        await self.persist_evidence()

    async def shutdown(self):
        if self.replay_worker: await self.replay_worker.shutdown()
        jobs=list(self.capture_jobs.values())
        for job in jobs: job.cancel()
        await asyncio.gather(*jobs,return_exceptions=True)

    async def run(self):
        while True:
            try:
                if self.scheduler:
                    await self.scheduler.submit(TaskEnvelope('observation-tick','observation'),self.tick)
                else: await self.tick()
            except asyncio.CancelledError: raise
            except Exception:
                self.last_error='观察处理失败，将重试；请查看任务状态'
            await asyncio.sleep(self.interval)
