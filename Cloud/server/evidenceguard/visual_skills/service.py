"""Durable scene drafts and foreground-camera observation, scoped to installation.

Existing replay/marker leases remain authoritative. Scenes never take them over.
All asynchronous results compare the exact revision before saving any effect.
"""
import asyncio
import copy
import hashlib
import io
import json
import time
import uuid
from PIL import Image
from .schema import LIMITATION, summary, Interpretation, Judgment


class SceneUnavailable(ValueError):
    """A user-facing capture diagnostic, never a provider validation dump."""


class VisualScenes:
    PERIOD = 15
    MAX_GAP = 90

    def __init__(self, store, captures, harness, proactive):
        self.store, self.captures, self.harness, self.proactive = store, captures, harness, proactive
        self.compiling = {}
        self.worker_lock = asyncio.Lock()
        with store.transaction():
            store.db.execute('CREATE TABLE IF NOT EXISTS visual_scenes (id TEXT PRIMARY KEY, client TEXT NOT NULL, due REAL NOT NULL, payload TEXT NOT NULL)')
            for scene in self.list_all():
                if scene['stage'] == 'generating':
                    scene.update(stage='describe', reason='上次整理被中断，原话已保存，请重新生成。')
                if scene['status'] == 'active':
                    scene.update(observation=self.empty_observation('服务恢复中，等待重新建立观察基线'))
                self.save(scene)

    @staticmethod
    def empty_observation(reason='等待新的画面'):
        return dict(state='unknown', reason=reason, armed=False, since=None, count=0,
                    lastAt=None, lastFrameId=None)

    def save(self, scene, due=None):
        self.store.db.execute('INSERT INTO visual_scenes VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET due=excluded.due,payload=excluded.payload',
                              (scene['id'], scene['clientId'], due if due is not None else scene.get('due', time.time()), json.dumps(scene, ensure_ascii=False)))

    def list_all(self, client=None):
        with self.store.lock:
            rows = self.store.db.execute('SELECT payload FROM visual_scenes' + (' WHERE client=?' if client else '') + ' ORDER BY rowid DESC', (client,) if client else ()).fetchall()
        return [json.loads(row[0]) for row in rows]

    def get(self, key, client):
        with self.store.lock:
            row = self.store.db.execute('SELECT payload FROM visual_scenes WHERE id=? AND client=?', (key, client)).fetchone()
        if not row: raise KeyError(key)
        return json.loads(row[0])

    def public(self, scene):
        value = {k: v for k, v in scene.items() if k not in {'clientId', 'requestId', 'inputs', 'due'}}
        value['summary'] = summary(scene['plan'])
        value['limitation'] = LIMITATION
        value['canActivate'] = bool(scene['stage'] == 'review' and scene['plan'] and scene['box'] and scene['frame']
                                   and not scene['question'] and not scene['unsupportedReason'] and self.harness.ready)
        return value

    def editable(self, key, client, revision):
        scene = self.get(key, client)
        if scene['revision'] != revision: raise ValueError('草稿已更新，请刷新后重试。')
        if scene['status'] != 'draft': raise ValueError('请新建草稿修改规则，当前任务保持原规则。')
        if scene['stage'] == 'generating': raise ValueError('正在整理需求，请稍候。')
        return scene

    async def create(self, client, body):
        key = 'scene-' + hashlib.sha256((client + ':' + body.requestId).encode()).hexdigest()[:32]
        try:
            scene = self.get(key, client)
            if scene['cameraId'] != body.cameraId or scene['inputs'][0] != body.message:
                raise ValueError('同一请求不能用于不同需求。')
            return scene
        except KeyError: pass
        devices = {m.id for m in await self.captures.cameras.manifests()}
        if body.cameraId not in devices: raise ValueError('请先选择已连接的摄像头。')
        if len(self.compiling) >= 4: raise ValueError('正在整理其他需求，请稍后重试。')
        scene = dict(id=key, clientId=client, cameraId=body.cameraId, inputs=[body.message], requestId=body.requestId,
                     prompt=body.message, revision=1, status='draft', stage='generating', plan=None, question='',
                     unsupportedReason='', reason='正在理解你的需求', frame=None, box=None,
                     createdAt=time.time(), observation=self.empty_observation(), evidenceIds=[])
        with self.store.transaction():
            # Device discovery awaited above. Recheck under the write lock so
            # concurrent HTTP retries cannot replace a draft or call the model twice.
            try:
                existing = self.get(key, client)
                if existing['cameraId'] != body.cameraId or existing['inputs'][0] != body.message:
                    raise ValueError('同一请求不能用于不同需求。')
                return existing
            except KeyError: pass
            if len(self.compiling) >= 4: raise ValueError('正在整理其他需求，请稍后重试。')
            self.save(scene)
        self.launch_compile(scene)
        return scene

    def interpret(self, key, client, body):
        existing = self.get(key, client)
        if existing['requestId'] == body.requestId:
            if existing['inputs'][-1] != body.message: raise ValueError('请求内容已改变，请重新提交。')
            return existing
        if len(self.compiling) >= 4: raise ValueError('正在整理其他需求，请稍后重试。')
        with self.store.transaction():
            scene = self.editable(key, client, body.revision)
            if len(scene['inputs']) >= 20 or sum(map(len, scene['inputs'])) + len(body.message) > 12000:
                raise ValueError('这份草稿修改较多，请用完整需求新建一份。')
            scene['inputs'].append(body.message)
            scene.update(revision=scene['revision']+1, requestId=body.requestId, stage='generating',
                         question='', unsupportedReason='', reason='正在更新这份需求', frame=None, box=None)
            self.save(scene)
        self.launch_compile(scene)
        return scene

    def launch_compile(self, scene):
        task = asyncio.create_task(self.compile(copy.deepcopy(scene)))
        self.compiling[scene['id']] = task
        task.add_done_callback(lambda _: self.compiling.pop(scene['id'], None))

    async def compile(self, original):
        try:
            result = Interpretation.model_validate(await self.harness.interpret(original)).model_dump()
            stage = 'select' if result['plan'] and not result['question'] and not result['unsupportedReason'] else 'describe'
            reason = result['unsupportedReason'] or result['question'] or '需求已整理，请在画面中框选'
        except asyncio.CancelledError: return
        except Exception:
            result = {}; stage = 'describe'; reason = '本次整理未完成，原话已保存，请重试。'
        with self.store.transaction():
            scene = self.get(original['id'], original['clientId'])
            if scene['revision'] != original['revision'] or scene['stage'] != 'generating': return
            scene.update(**result, stage=stage, reason=reason)
            self.save(scene)

    async def frame(self, key, client, revision):
        original = self.editable(key, client, revision)
        if not original['plan'] or original['question'] or original['unsupportedReason']:
            raise ValueError('请先补充完整需求。')
        receipt = await self.captures.capture(original['cameraId'], purpose='为用户框选场景获取新画面')
        self.validate_frame(receipt)
        raw, _, _ = self.store.media(receipt['mediaId'])
        with Image.open(io.BytesIO(raw)) as image:
            receipt['width'], receipt['height'] = image.size
        with self.store.transaction():
            scene = self.editable(key, client, revision)
            scene.update(frame=receipt, box=None, revision=revision+1, stage='select', reason='请拖动框出目标或关注区域')
            self.save(scene)
        return scene

    @staticmethod
    def validate_frame(receipt, age=20):
        if not receipt or receipt.get('status') != 'completed':
            raise SceneUnavailable((receipt or {}).get('reason') or '没有取得新画面，请连接摄像头后重试。')
        if receipt.get('sourceType') != 'official_live_ios':
            raise SceneUnavailable('请使用 iOS 直播的新画面，不能用事件缩略图或测试图片开启场景。')
        observed = receipt.get('capturedAt') or receipt.get('sampledAt')
        if observed is None or not -0.5 <= time.time() - observed <= age:
            raise SceneUnavailable('画面已过期，请重新获取画面并框选。')

    def select(self, key, client, body):
        with self.store.transaction():
            scene = self.editable(key, client, body.revision)
            self.validate_frame(scene['frame'], age=300)
            if scene['frame']['frameId'] != body.frameId: raise ValueError('画面已变化，请重新框选。')
            scene.update(box=body.box.model_dump(), revision=scene['revision']+1, stage='review', reason='请确认下面的提醒条件')
            self.save(scene)
        return scene

    async def activate(self, key, client, revision):
        with self.store.transaction():
            scene = self.get(key, client)
            if scene['status'] == 'active' and scene.get('confirmedRevision') == revision: return scene
            scene = self.editable(key, client, revision)
            if not self.public(scene)['canActivate']: raise ValueError('需求、框选或模型尚未就绪，草稿已保留。')
            self.validate_frame(scene['frame'], age=300)
        manifests = await self.captures.cameras.manifests()
        device = next((m for m in manifests if m.id == scene['cameraId']), None)
        if not device or device.connection != 'online': raise ValueError('请保持 App 前台且画面已连接，再开启看护。')
        self.store.capture_context(scene['cameraId'])  # Preserve legacy camera leases.
        with self.store.transaction():
            scene = self.editable(key, client, revision)
            if any(s['status'] == 'active' and s['cameraId'] == scene['cameraId'] for s in self.list_all()):
                raise ValueError('这台摄像头已有运行中的自定义场景，请先暂停它。')
            scene.update(status='active', revision=revision+1, confirmedRevision=revision,
                         observation=self.empty_observation('已开启，等待建立新观察基线'), reason='已开启，等待新的画面')
            self.save(scene, time.time())
        return scene

    def pause(self, key, client, revision):
        with self.store.transaction():
            scene = self.get(key, client)
            if scene['revision'] != revision: raise ValueError('任务已更新，请刷新。')
            if scene['status'] not in {'active', 'paused'}: raise ValueError('这项场景没有运行。')
            scene.update(status='draft', revision=revision+1, stage='select', frame=None, box=None,
                         reason='已暂停；再次开启前需要重新取图和框选', observation=self.empty_observation('已暂停'))
            self.save(scene)
        return scene

    async def step(self, now=None):
        now = time.time() if now is None else now
        async with self.worker_lock:
            with self.store.transaction():
                row = self.store.db.execute("SELECT payload FROM visual_scenes WHERE due<=? AND json_extract(payload,'$.status')='active' ORDER BY due LIMIT 1", (now,)).fetchone()
                if not row: return False
                original = json.loads(row[0]); self.save(original, now + self.PERIOD)
            receipt = None
            try:
                receipt = await self.captures.capture(original['cameraId'], purpose='用户开启的自定义场景观察')
                self.validate_frame(receipt)
                if receipt.get('viewRevision') != original['frame'].get('viewRevision'):
                    raise SceneUnavailable('摄像头视角已变化，请暂停并重新框选。')
                result = Judgment.model_validate(await self.harness.observe(original, receipt, self.store)).model_dump()
                if not result['regionClear'] or (result['state']=='inside' and not result['identityClear']): result['state']='unknown'
            except asyncio.CancelledError: raise
            except Exception as error:
                result = dict(state='unknown', reason=str(error) if isinstance(error, SceneUnavailable) else '观察暂未完成，等待新画面')
            with self.store.transaction():
                scene = self.get(original['id'], original['clientId'])
                if scene['revision'] != original['revision'] or scene['status'] != 'active': return True
                alert = self.advance(scene, result, receipt, time.time())
                if alert: self.publish(scene, receipt)
                self.save(scene, time.time() + self.PERIOD)
            return True

    def advance(self, scene, result, receipt, now):
        state = result['state']; old = scene['observation']; plan = scene['plan']
        observed = (receipt or {}).get('capturedAt') or (receipt or {}).get('sampledAt')
        frame = (receipt or {}).get('frameId')
        if state == 'unknown' or observed is None or not -0.5 <= now-observed <= self.MAX_GAP:
            scene['observation'] = self.empty_observation(result['reason'])
            return False
        if frame == old['lastFrameId'] or (old['lastAt'] is not None and observed <= old['lastAt']): return False
        if old['lastAt'] is not None and observed-old['lastAt'] > self.MAX_GAP:
            old = self.empty_observation('观察有间断，重新建立基线')
        desired = 'inside' if plan['trigger'] == 'enters' else 'outside'
        current = dict(state=state, reason=result['reason'], lastAt=observed, lastFrameId=frame,
                       armed=old['armed'], since=old['since'], count=old['count'])
        if state != desired:
            current.update(armed=True, since=None, count=0)
        elif current['armed']:
            current.update(since=old['since'] if old['since'] is not None else observed, count=old['count']+1)
        scene['observation'] = current
        if current['armed'] and current['count'] >= 2 and observed-current['since'] >= plan['confirmationSeconds']:
            current.update(armed=False, since=None, count=0)
            if plan['completion'] == 'once': scene['status'] = 'completed'
            return True
        return False

    def publish(self, scene, receipt):
        key = 'scene-evidence-' + uuid.uuid4().hex
        at = receipt.get('capturedAt') or receipt['sampledAt']
        evidence = dict(id=key, skillId='', cameraId=scene['cameraId'], capturedAt=at,
                        relation=scene['observation']['state'], reason=scene['observation']['reason'],
                        imageUrl=receipt['imageUrl'], revision=scene['revision'], sourceType=receipt['sourceType'],
                        sceneId=scene['id'], frameId=receipt['frameId'], timestampMeaning=receipt['timestampMeaning'])
        self.store.db.execute('INSERT INTO evidence VALUES (?,?,?,?)', (key, '', at, json.dumps(evidence, ensure_ascii=False)))
        scene['evidenceIds'] = [*scene['evidenceIds'], key][-30:]
        body = f"{scene['plan']['title']}：{scene['observation']['reason']}。已满足你设置的采样确认条件，点开查看画面。"
        message = dict(id='message-'+key, jobId=key, runId=None, role='assistant', origin='proactive',
                       kind='visual_scene', title=scene['plan']['title'], body=body, why='用户确认开启的场景条件已满足',
                       sources=[dict(id='evidence:'+key, type='camera_evidence', evidenceId=key,
                                     cameraId=scene['cameraId'], observedAt=at, sourceType=receipt['sourceType'],
                                     imageUrl=receipt['imageUrl'], limitation=LIMITATION)],
                       createdAt=time.time(), read=False, feedback=None, skillId=None, triggerKey=key,
                       delivery='in_app', valueScore=None)
        encoded=json.dumps(message, ensure_ascii=False)
        self.store.db.execute('INSERT INTO assistant_messages VALUES (?,?,?,?,?)', (message['id'],scene['clientId'],key,message['createdAt'],encoded))
        self.store.db.execute('INSERT INTO personal_inbox VALUES (?,?,?,?)', (message['id'],scene['clientId'],key,encoded))
        if self.proactive.push: self.proactive.push.message(scene['clientId'], message, {'expiresAt':time.time()+3600})

    async def run(self):
        while True:
            try: await self.step()
            except asyncio.CancelledError: raise
            except Exception: await asyncio.sleep(5)
            await asyncio.sleep(2)

    async def shutdown(self):
        tasks = list(self.compiling.values())
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
