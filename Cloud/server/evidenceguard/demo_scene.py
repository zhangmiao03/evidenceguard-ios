"""Opt-in synthetic scenes for the isolated mobile demo, never an SDK import.

Three saved samples represent 0/3/6 seconds. They exercise real visual review and
the normal proactive policy, but cannot arm a Skill or claim a removal action.
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class SceneRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    requestId: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_-]+$')
    scenario: Literal['parcel_absent', 'occluded', 'unchanged']


class DemoScenes:
    TITLES = {'parcel_absent':'包裹从可见区域消失', 'occluded':'关注区域被遮挡', 'unchanged':'包裹持续可见'}
    def __init__(self, store, visual, proactive):
        self.store, self.visual, self.proactive = store, visual, proactive
        self.enabled = os.getenv('EG_ENABLE_SYNTHETIC_DEMO') == '1'
        self.assets = Path(__file__).parent / 'fixtures' / 'parcel'
        with store.transaction():
            store.db.execute('CREATE TABLE IF NOT EXISTS demo_scenes (id TEXT PRIMARY KEY, client TEXT NOT NULL, created REAL NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL)')
            store.db.execute("UPDATE demo_scenes SET status='pending' WHERE status='running'")

    def scene(self, key):
        with self.store.lock:
            row = self.store.db.execute('SELECT status,payload FROM demo_scenes WHERE id=?', (key,)).fetchone()
        return (json.loads(row[1]) | {'status':row[0]}) if row else None

    def snapshot(self, client):
        with self.store.lock:
            rows = self.store.db.execute('SELECT id FROM demo_scenes WHERE client=? ORDER BY created DESC LIMIT 8', (client,)).fetchall()
        return dict(enabled=self.enabled, scenes=[self.public(self.scene(r[0])) for r in rows])

    def public(self, scene):
        result = {k:v for k,v in scene.items() if k not in {'client','requestId'}}
        with self.store.lock:
            row = self.store.db.execute('SELECT status,payload FROM proactive_jobs WHERE client=? AND dedupe=?', (scene['client'],scene['id'])).fetchone()
            message = self.store.db.execute('SELECT id FROM assistant_messages WHERE client=? AND job_id=(SELECT id FROM proactive_jobs WHERE client=? AND dedupe=?)', (scene['client'],scene['client'],scene['id'])).fetchone()
        result['policyStatus'] = row[0] if row else None
        job = json.loads(row[1]) if row else {}
        result['policyReason'] = job.get('reason')
        result['valueScore'] = job.get('assessment',{}).get('valueScore')
        result['assistantDraft'] = job.get('assessment',{}).get('body')
        result['messageId'] = message[0] if message else None
        return result

    def start(self, client, body, now=None):
        if not self.enabled: raise KeyError('demo disabled')
        now = time.time() if now is None else now
        key = 'demo-'+hashlib.sha256((client+'\0'+body.requestId).encode()).hexdigest()[:32]
        with self.store.transaction():
            old = self.scene(key)
            if old:
                if old['scenario'] != body.scenario: raise ValueError('同一测试请求不能改变场景')
                return self.public(old)
            running = self.store.db.execute("SELECT 1 FROM demo_scenes WHERE status IN ('pending','running')").fetchone()
            if running: raise ValueError('已有测试场景正在核验，请稍后再试')
            start = datetime.fromtimestamp(now,timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
            count = self.store.db.execute('SELECT COUNT(*) FROM demo_scenes WHERE client=? AND created>=?', (client,start)).fetchone()[0]
            if count >= 6: raise ValueError('今天已运行6次测试，证据仍可查看；请明天再试')
            states = ['present','absent','absent'] if body.scenario == 'parcel_absent' else ['present','occluded','occluded'] if body.scenario == 'occluded' else ['present']*3
            scene = dict(id=key, client=client, scenario=body.scenario, title=self.TITLES[body.scenario],
                         createdAt=now, sourceType='synthetic_demo', cameraId='demo-porch',
                         sampleIntervalSeconds=3, attempts=0, samples=[], status='pending',
                         reason='等待视觉模型核验；这些是合成测试图片，不是摄像头录像')
            for index,state in enumerate(states):
                evidence_id = key+'-'+str(index)
                media = self.store.save_media(dict(device_id='demo-porch', frame_id=evidence_id,
                                                    source_type='synthetic_demo', captured_at=None,
                                                    generated_at=now, relative_seconds=index*3),
                                              (self.assets/(state+'.jpg')).read_bytes(), 'image/jpeg')
                item = dict(id=evidence_id, skillId='', cameraId='demo-porch', capturedAt=now,
                            relation='unknown', reason=f'合成测试的第{index+1}张样本，模拟时间{index*3}s；尚未核验。生成时间不是摄像头采集时间。',
                            revision=0, sourceType='synthetic_demo', imageUrl=media['imageUrl'], mediaStatus='saved',
                            frameId=evidence_id, timestampMeaning='generated')
                self.store.db.execute('INSERT INTO evidence VALUES (?,?,?,?)', (evidence_id,'',now,json.dumps(item,ensure_ascii=False)))
                scene['samples'].append(dict(id=evidence_id,imageUrl=media['imageUrl'],relativeSeconds=index*3))
            self.store.db.execute('INSERT INTO demo_scenes VALUES (?,?,?,?,?)', (key,client,now,'pending',json.dumps(scene,ensure_ascii=False)))
        return self.public(scene)

    def sources(self, key):
        scene = self.scene(key)
        if not scene or scene['status'] != 'completed': return []
        result = [dict(id=key,type='task_state',name='门廊合成测试',result=scene['status'],revision=1,
                       sourceType='synthetic_demo',reason=scene['reason'],visualReview=scene.get('review'),
                       userGoal='测试请求：关注门廊中的纸箱；如果样本显示区域状态变化，说明变化和资料缺口，建议用户查看证据。若没有变化，不打扰。',
                       limitation='只测试离散图片的判断和提醒编排；没有运行或绑定任何真实摄像头任务')]
        for sample in scene['samples']:
            result.append(dict(id='evidence:'+sample['id'],type='camera_evidence',evidenceId=sample['id'],
                               cameraId=scene['cameraId'],sourceType='synthetic_demo',imageUrl=sample['imageUrl'],
                               observedAt=None,relativeSeconds=sample['relativeSeconds'],visualReview=scene['review'],
                               limitation='模拟时间，以s计；并非真实拍摄时间，不能确认样本间的拿走动作'))
        return result

    async def step(self):
        if not self.enabled: return False
        with self.store.transaction():
            row = self.store.db.execute("SELECT id FROM demo_scenes WHERE status='pending' ORDER BY created LIMIT 1").fetchone()
            if not row: return False
            scene = self.scene(row[0]); scene['attempts'] += 1
            self.store.db.execute("UPDATE demo_scenes SET status='running',payload=? WHERE id=?", (json.dumps(scene,ensure_ascii=False),scene['id']))
        result = await self.visual.review(scene['cameraId'],scene['id'],[(s['imageUrl'].split('/')[-1],s['relativeSeconds']) for s in scene['samples']])
        with self.store.transaction():
            scene.update(review=result, reason=result.get('reason') or '已核验三张合成测试图片；没有确认连续动作或启用真实守护')
            self.store.db.execute('UPDATE demo_scenes SET status=?,payload=? WHERE id=?', (result['status'],json.dumps(scene,ensure_ascii=False),scene['id']))
            if result['status']=='completed':
                review = result['review']
                for sample in scene['samples']:
                    row = self.store.db.execute('SELECT payload FROM evidence WHERE id=?',(sample['id'],)).fetchone()
                    evidence = json.loads(row[0]); evidence['reason'] = review['visible']+'\n'+review['uncertainties']+f"\n合成测试样本 {sample['relativeSeconds']}s；非实拍，无连续动作结论。"
                    self.store.db.execute('UPDATE evidence SET payload=? WHERE id=?',(json.dumps(evidence,ensure_ascii=False),sample['id']))
                if self.proactive.personal.profile(scene['client'])['preferences']['enabled']:
                    self.proactive.enqueue(scene['client'],scene['id'],'demo_event','合成测试：'+scene['title'],scene['reason'],time.time())
                else:
                    scene['reason'] += '；主动提醒未开启，仅保存证据'
                    self.store.db.execute('UPDATE demo_scenes SET payload=? WHERE id=?',(json.dumps(scene,ensure_ascii=False),scene['id']))
        return True

    async def run(self):
        while True:
            try: await self.step()
            except asyncio.CancelledError: raise
            except Exception:
                with self.store.transaction():
                    self.store.db.execute("UPDATE demo_scenes SET status='unavailable' WHERE status='running'")
            await asyncio.sleep(2)
