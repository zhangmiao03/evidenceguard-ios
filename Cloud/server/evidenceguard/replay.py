"""Bounded replay execution sharing Skill ownership, epochs, alerts and evidence."""
from __future__ import annotations
import asyncio, copy, json, time, uuid
from pathlib import Path
from .video.providers import ProviderError

class ReplayWorker:
    def __init__(self,store,videos,camera_service):
        self.store,self.videos,self.camera_service=store,videos,camera_service
        self.jobs={}; self.gate=asyncio.Semaphore(2)
        for s in store.skills():
            if s['status']=='active' and s.get('replay'):
                s.update(status='paused',result='unknown',resultReason='服务重启中断回放，请手动恢复并重新建立基线')
                store.save_skill(s);store.event(s['id'],'replay_interrupted',{})

    def valid(self,skill,generation):
        current=self.store.skill(skill['id'])
        return current if current and current['status']=='active' and current.get('executionEpoch')==skill.get('executionEpoch') and current.get('replayState',{}).get('generation',0)==generation and current.get('replayState',{}).get('online',True) else None

    async def tick(self):
        active={s['id']:s for s in self.store.skills() if s['status']=='active' and s.get('replay')}
        for sid,(job,epoch,generation) in list(self.jobs.items()):
            s=active.get(sid)
            if not s or s.get('executionEpoch')!=epoch or s.get('replayState',{}).get('generation',0)!=generation or not s.get('replayState',{}).get('online',True): job.cancel()
        for sid,s in active.items():
            state=s.get('replayState',{})
            if sid in self.jobs or not state.get('online',True) or time.time()<state.get('nextAt',0): continue
            generation=state.get('generation',0)
            task=asyncio.create_task(self.advance(s,generation)); self.jobs[sid]=(task,s['executionEpoch'],generation)
            task.add_done_callback(lambda _,key=sid:self.jobs.pop(key,None))

    async def advance(self,skill,generation):
        try:
            async with self.gate:
                if not self.valid(skill,generation):return
                from .schemas import SkillRules
                from .timing import accumulate
                rules=SkillRules.model_validate(skill['rules']);period=rules.sampleIntervalSeconds
                state=copy.deepcopy(skill.get('replayState',{}));at=state.get('nextSampleAt',0.)
                cp=copy.deepcopy(skill.get('evaluation',{}))
                if cp.get('epoch')!=skill['executionEpoch']:cp=dict(epoch=skill['executionEpoch'],armed=False,candidate={})
                recording=self.videos.db.recording(skill['replay']['recordingId'])
                if at>=recording['duration'] or state.get('modelCalls',0)>=20:
                    self.finish(skill,generation,'已完成全部计划采样' if at>=recording['duration'] else '达到20次采样预算');return
                began=time.time();sample=await self.camera_service.replay_sample(skill,at)
                baseline=not cp.get('armed')
                self.store.event(skill['id'],'replay_observing',{'sampleAt':at,'sampleIntervalSeconds':period,'baseline':baseline})
                query=f"当前原片采样位置 {at:g} s。每 {period} s 抽样。目标：{skill['target']['description']}。初始目标框：{json.dumps(skill['target']['box'])}。只判断当前区域状态，采样之间不可见，不能推断精确动作时间。"
                judgment=None;error=None
                try:judgment=await self.videos.vision.observe_frame(sample.path,query,cp.get('referencePath'))
                except Exception as e:error={'code':getattr(e,'code',type(e).__name__),'detail':str(e) if isinstance(e,ProviderError) else '采样图复核失败','attempts':getattr(e,'diagnostics',[])}
                video=None;would_trigger=False
                if judgment and judgment['state']=='absent' and cp.get('armed'):
                    candidate=accumulate(cp.get('candidate',{}),'absent',at,str(sample.path),period)
                    would_trigger=candidate.get('span',0)>=rules.confirmationSeconds
                    if would_trigger:
                        video=await self.camera_service.replay_window(skill,max(0,at-12),at)
                with self.store.transaction():
                    current=self.valid(skill,generation)
                    if not current:return
                    state.update(cursor=at,nextSampleAt=at+period,modelCalls=state.get('modelCalls',0)+1,nextAt=max(time.time(),began+period))
                    current['lastObservedAt']=time.time()
                    if error:
                        state['errors']=state.get('errors',0)+1;cp.update(armed=False,candidate={});cp.pop('referencePath',None)
                        current.update(result='unknown',resultReason='采样图复核失败，重新建立基线，不把失败当成离区')
                        self.store.event(skill['id'],'replay_model_failed',error)
                        if state['errors']>=3:current.update(status='paused',resultReason='连续3次采样复核失败，已暂停')
                    else:
                        state['errors']=0;presence=judgment['state']
                        if presence=='present':
                            cp.update(armed=True,candidate={},lastPresentAt=at,referencePath=str(sample.path))
                            current.update(result='confirmed',resultReason=f'{at:g} s 采样：目标在关注区域内')
                        elif presence=='absent' and cp.get('armed'):
                            cp['candidate']=accumulate(cp.get('candidate',{}),'absent',at,str(sample.path),period)
                            span=cp['candidate'].get('span',0)
                            current.update(result='unknown',resultReason=f'区域内未见目标，采样确认跨度 {span:g}/{rules.confirmationSeconds} s')
                            if would_trigger:
                                cp['latched']=True
                                current.update(result='needs_attention',alert='open',status='completed',resultReason=f'间隔 {period} s 的抽样在 {span:g} s 跨度内均未见目标，请核验；不能确认离区动作的精确时间')
                                self.evidence(current,video,at,judgment)
                                self.store.event(skill['id'],'alert_opened',{'sourceType':'replay','confirmedAtSeconds':at,'possibleChangeStart':cp.get('lastPresentAt'),'firstAbsentAt':cp['candidate']['since'],'timestampMeaning':'sample_confirmation'})
                        else:
                            cp['candidate']={}
                            current.update(result='unknown',resultReason='采样无法确认或缺少在场基线，保留判断')
                        self.store.event(skill['id'],'replay_model_completed',{'windowStart':at,'windowEnd':at,'sampleAt':at,'baseline':baseline,'verdict':'matched' if (baseline and presence=='present') or (not baseline and presence=='absent') else 'uncertain' if presence=='unknown' else 'not_matched','presence':presence,'eventTime':None,'summary':judgment['summary'],'diagnostics':judgment.get('diagnostics',[])})
                    current.update(replayState=state,evaluation=cp);self.store.save_skill(current)
                    if current['status']=='active' and at+period>=recording['duration']:self.finish(current,generation,'已完成全部计划采样，片尾不足一个间隔不追加采样')
        except asyncio.CancelledError:
            self.store.event(skill['id'],'replay_observation_cancelled',{'epoch':skill['executionEpoch']});raise
        except Exception as error:
            with self.store.transaction():
                current=self.valid(skill,generation)
                if current:
                    current.update(status='paused',result='unknown',resultReason='采样输入处理失败，已暂停')
                    self.store.save_skill(current);self.store.event(skill['id'],'replay_input_failed',{'code':type(error).__name__})

    def finish(self,skill,generation,reason):
        current=self.valid(skill,generation)
        if not current:return
        current.update(status='completed',result='needs_attention' if current['alert']=='open' else 'unknown',resultReason=reason+'；已有提醒请核验' if current['alert']=='open' else reason+'；未形成确认提醒，不代表没有发生')
        self.store.save_skill(current);self.store.event(skill['id'],'replay_finished',{})

    def evidence(self,skill,window,event_time,judgment):
        rid='replay-'+uuid.uuid4().hex
        r=self.videos.db.recording(window.recording_id)
        item=dict(id=rid,skillId=skill['id'],cameraId=window.device_id,capturedAt=time.time(),relation='outside',reason=skill['resultReason'],
            imageUrl=None,revision=skill['revision'],sourceType='replay',mediaStatus='video',frameId=rid,
            recordingId=window.recording_id,clipStart=window.start,clipEnd=window.end,seekSeconds=event_time-window.start,
            originalEventTime=event_time,timestampMeaning='sample_confirmation',recordedAt=r.get('recordedAt'),videoPath=str(window.path),videoUrl=f'/api/replay-evidence/{rid}/video',modelSummary=judgment['summary'])
        self.store.db.execute('INSERT INTO evidence VALUES (?,?,?,?)',(rid,skill['id'],item['capturedAt'],json.dumps(item,ensure_ascii=False)))

    async def transport(self,skill_id,online):
        async with self.camera_service.transition():
            s=self.store.skill(skill_id)
            if not s or not s.get('replay') or s['status'] not in {'active','paused'}: raise ValueError('当前任务不是可切换输入的回放任务')
            state=s.get('replayState',{});state.update(online=online,generation=state.get('generation',0)+1)
            s.update(replayState=state,evaluation={},result='unknown',resultReason='回放输入已恢复，等待重建基线' if online else '回放输入已断开，保留判断')
            self.store.save_skill(s);self.store.event(skill_id,'replay_transport_changed',{'online':online})
            return s

    async def shutdown(self):
        jobs=[j[0] for j in self.jobs.values()]
        for job in jobs:job.cancel()
        await asyncio.gather(*jobs,return_exceptions=True)
