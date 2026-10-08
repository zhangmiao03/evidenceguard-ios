"""Read-only stored-video trials reuse the live replay engine in an isolated store.
No live camera calls, ownership changes, notifications or production evidence writes.
"""
from __future__ import annotations
import asyncio,copy,json,tempfile,time,uuid
from pathlib import Path
from contextlib import asynccontextmanager
from .store import Store
from .replay import ReplayWorker
from .camera.contracts import CameraCommandContext
from .camera.adapters.replay import ReplayAdapter
from .skill_capabilities import assess,fingerprint

class TrialInput:
    def __init__(self,videos):self.adapter=ReplayAdapter(videos)
    @asynccontextmanager
    async def transition(self):yield
    async def replay_sample(self,skill,at):
        context=CameraCommandContext(uuid.uuid4().hex,skill['id'],skill['executionEpoch'],time.time()+120)
        return await self.adapter.sample(skill['devices'][0],skill['replay']['recordingId'],at,context,skill['regions'][skill['devices'][0]])
    async def replay_window(self,skill,start,end):
        context=CameraCommandContext(uuid.uuid4().hex,skill['id'],skill['executionEpoch'],time.time()+120)
        return await self.adapter.window(skill['devices'][0],skill['replay']['recordingId'],start,end,context,skill['regions'][skill['devices'][0]])

class SkillTrials:
    def __init__(self,store,videos):
        self.store,self.videos=store,videos;self.jobs={};self.gate=asyncio.Semaphore(1)
        with store.transaction():store.db.execute('CREATE TABLE IF NOT EXISTS skill_trials (id TEXT PRIMARY KEY, skill_id TEXT NOT NULL, created_at REAL NOT NULL, payload TEXT NOT NULL)')
        for r in self.list():
            if r['status'] in {'queued','running'}:
                r.update(status='interrupted',summary='服务重启中断试跑，请重新运行。');self.save(r)
    def save(self,r):
        with self.store.transaction():self.store.db.execute('INSERT INTO skill_trials VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',(r['id'],r['skillId'],r['createdAt'],json.dumps(r,ensure_ascii=False)))
    def read(self,rid):
        with self.store.lock:row=self.store.db.execute('SELECT payload FROM skill_trials WHERE id=?',(rid,)).fetchone()
        if not row:raise KeyError(rid)
        return json.loads(row[0])
    def list(self,sid=None):
        with self.store.lock:
            rows=self.store.db.execute('SELECT payload FROM skill_trials'+(' WHERE skill_id=?' if sid else '')+' ORDER BY created_at DESC LIMIT 100', (sid,) if sid else ()).fetchall()
        return [json.loads(row[0]) for row in rows]
    def current(self,r):
        s=self.store.skill(r['skillId'])
        try:return bool(s and s['revision']==r['revision'] and fingerprint(s,self.videos)==r['fingerprint'])
        except (KeyError,ValueError):return False
    def public(self,r):
        value={k:v for k,v in r.items() if k not in {'videoPath','fingerprint'}}
        value['stale']=not self.current(r)
        observations=r.get('observations',[])
        negative_coverage=bool(observations) and all(o.get('presence') in {'present','absent'} for o in observations) and observations[-1]['end']-observations[0]['start']>=r.get('confirmationSeconds',6) and r.get('samplingComplete',False)
        value['acceptancePassed']=r.get('status')=='completed' and r.get('baselineEstablished',False) and not r.get('failureCount',0) and r.get('expectedOutcome') in {'alert','no_alert'} and r.get('wouldAlert',False)==(r.get('expectedOutcome')=='alert') and (r.get('expectedOutcome')=='alert' or negative_coverage)
        value['canConfirm']=value['acceptancePassed'] and not value['stale'] and r['status']=='completed' and r.get('baselineEstablished',False) and not r.get('failureCount',0)
        return value
    def start(self,sid,revision,expected_outcome="explore"):
        s=self.store.skill(sid)
        if not s or s['status']!='draft' or s['revision']!=revision:raise ValueError('请先保存最新草案再试跑。')
        capability=assess(s,self.videos)
        if not capability['canTrial']:raise ValueError('；'.join(capability['blockers']) or '当前任务不支持录像试跑。')
        for r in self.list(sid):
            if r['status'] in {'queued','running'} and self.current(r) and r.get('expectedOutcome')==expected_outcome:return self.public(r)
        if len(self.jobs)>=2:raise ValueError('试跑队列已满，请等待或取消现有试跑。')
        if expected_outcome not in {'explore','alert','no_alert'}:raise ValueError('无效的人工预期')
        rid='trial-'+uuid.uuid4().hex
        r=dict(id=rid,skillId=sid,revision=revision,expectedOutcome=expected_outcome,fingerprint=fingerprint(s,self.videos),createdAt=time.time(),status='queued',
            sampleIntervalSeconds=s['rules']['sampleIntervalSeconds'],confirmationSeconds=s['rules']['confirmationSeconds'],sourceRecordingId=s['replay']['recordingId'],cameraId=s['devices'][0],sourceDuration=self.videos.db.recording(s['replay']['recordingId'])['duration'],summary='等待试跑；只读录像，不占用摄像头。',contract=capability['contract'],observations=[],baselineEstablished=False,failureCount=0,wouldAlert=False,timestampMeaning='sample_confirmation',
            eventTime=None,clipStart=None,clipEnd=None,videoUrl=None,model=getattr(self.videos.vision,'model',''),
            limitations=['人工预期只标注本段是否应提醒，不代表独立测试集的准确率。','每隔N秒的抽样不能证明间隔内发生了什么。','报告仅适用于当前草案、录像及模型配置。'])
        self.save(r);task=asyncio.create_task(self.execute(r,copy.deepcopy(s)));self.jobs[rid]=task
        task.add_done_callback(lambda _:self.jobs.pop(rid,None));return self.public(r)
    async def execute(self,r,snapshot):
        began=time.monotonic()
        try:
            async with self.gate,asyncio.timeout(360):
                if not self.current(r):r.update(status='stale',summary='草案已修改，试跑停止。');return
                r.update(status='running',summary='正在按时间顺序分析已存录像。');self.save(r)
                with tempfile.TemporaryDirectory(prefix='eg-trial-') as directory:
                    sandbox=Store(Path(directory)/'trial.sqlite')
                    worker=ReplayWorker(sandbox,self.videos,TrialInput(self.videos))
                    try:
                        s=copy.deepcopy(snapshot);s.update(status='draft',replayState=dict(cursor=0,online=True,generation=0,modelCalls=0),alert='none',evaluation={})
                        sandbox.save_skill(s);sandbox.confirm(s['id'],s['revision'])
                        while sandbox.skill(s['id'])['status']=='active':
                            if not self.current(r):r.update(status='stale',summary='草案或模型配置已变化，试跑停止。');return
                            # Share history-video verification capacity; never enter camera command lanes.
                            async with self.videos.verify_gate:await worker.advance(sandbox.skill(s['id']),0)
                            if not self.current(r):r.update(status='stale',summary='草案已变化，旧试跑结果不再有效。');return
                            events=sandbox.events(s['id'])
                            r['observations']=[dict(start=e['payload']['windowStart'],end=e['payload']['windowEnd'],baseline=e['payload']['baseline'],verdict=e['payload']['verdict'],sampleAt=e['payload'].get('sampleAt'),presence=e['payload'].get('presence'),eventTime=e['payload'].get('eventTime'),summary=e['payload']['summary']) for e in events if e['type']=='replay_model_completed']
                            r['baselineEstablished']=any(o['baseline'] and o['verdict']=='matched' for o in r['observations'])
                            failures=[e['payload'] for e in events if e['type'] in {'replay_model_failed','replay_input_failed'}]
                            r.update(failureCount=len(failures),failures=failures,cursor=sandbox.skill(s['id'])['replayState']['cursor']);self.save(r)
                        final=sandbox.skill(s['id']);evidence=sandbox.evidence()
                        r.update(wouldAlert=bool(evidence),stopReason=final['resultReason'],samplingComplete=final.get('replayState',{}).get('nextSampleAt',0)>=r['sourceDuration'])
                        r['limitations'].append(f"实际只观察到原片 {r.get('cursor',0):.2f} / {r['sourceDuration']:.2f} 秒；首次提醒或观察预算耗尽可能提前结束。")
                        if final['status']=='paused' or r['failureCount']:
                            r.update(status='failed',summary='试跑存在输入或模型失败，不能作为启用依据；请查看记录并重试。')
                        else:
                            r.update(status='completed',wouldAlert=bool(evidence),summary='会形成区域状态提醒，请播放核验。' if evidence else '本段未形成提醒；不代表其他场景不会误报或漏报。')
                            if not r['baselineEstablished']:r['summary']='没有建立清晰的目标在场基线，请调整圈选或更换录像后重试。'
                            elif not evidence and final.get('evaluation',{}).get('candidate',{}):
                                span=final['evaluation']['candidate'].get('span',0)
                                r['summary']=f'已观察到区域内未见目标，但确认跨度仅 {span:g} / {r["confirmationSeconds"]} s，未形成提醒。请提供移出后仍有足够清晰采样的录像。'
                        if evidence:
                            e=evidence[0];r.update(eventTime=e['originalEventTime'],clipStart=e['clipStart'],clipEnd=e['clipEnd'],videoPath=e['videoPath'],videoUrl=f'/api/skill-trials/{r["id"]}/video')
                    finally:await worker.shutdown();sandbox.close()
        except asyncio.CancelledError:r.update(status='cancelled',summary='试跑已取消，草案和原守护任务保持不变。')
        except TimeoutError:r.update(status='failed',summary='试跑超过6分钟上限，请缩短录像后重试。',failureCount=r.get('failureCount',0)+1)
        except Exception:r.update(status='failed',summary='试跑处理失败，请检查输入后重试。',failureCount=r.get('failureCount',0)+1)
        finally:
            r['elapsedSeconds']=round(time.monotonic()-began,2);self.save(r)
    async def cancel(self,rid):
        if task:=self.jobs.get(rid):task.cancel();await asyncio.gather(task,return_exceptions=True)
        r=self.read(rid)
        if r['status'] in {'queued','running'}:
            r.update(status='cancelled',summary='试跑已取消，草案和原守护任务保持不变。');self.save(r)
        return self.public(r)
    def require_review(self,s,trial_id,reviewed):
        if not trial_id or not reviewed:raise ValueError('请先完成当前草案的录像试跑，并确认已查看报告。')
        r=self.read(trial_id)
        if r['skillId']!=s['id'] or not self.public(r)['canConfirm']:raise ValueError('试跑报告未就绪或已过期，请重新试跑当前草案。')
    async def shutdown(self):
        tasks=list(self.jobs.values())
        for t in tasks:t.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
