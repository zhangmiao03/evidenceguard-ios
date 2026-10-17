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
from .audit import GuardRun, event, frame_reference


class SceneUnavailable(ValueError):
    """A user-facing capture diagnostic, never a provider validation dump."""


class VisualScenes:
    PERIOD = 15
    MAX_GAP = 90
    RESULT_TTL = 60
    HEALTH_GRACE = 120

    def __init__(self, store, captures, harness, proactive):
        self.store, self.captures, self.harness, self.proactive = store, captures, harness, proactive
        self.compiling = {}
        self.endpoint_vision = None
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
        value = {k: v for k, v in scene.items() if k not in {'clientId', 'requestId', 'inputs', 'due', 'healthSince', 'healthNotified'}}
        value['summary'] = summary(scene['plan'])
        value['limitation'] = LIMITATION
        value['canActivate'] = bool(scene['stage'] == 'review' and scene['plan'] and scene['box'] and scene['frame']
                                   and not scene['question'] and not scene['unsupportedReason'] and self.harness.ready)
        value['result'] = self.result(scene)
        value['triggerCategory'] = 'event'
        value['endpointVision'] = self.endpoint_vision.configuration() if self.endpoint_vision else {'ready':False}
        return value

    async def analyze_endpoints(self, key, client, revision, *, include_depth=False, run=None):
        """Only this guard's stored reference and last accepted sample are eligible.

        Never lets a model nominate an arbitrary media ID, path, device or ROI.
        It also never captures implicitly when evidence is missing.
        """
        from ..vision.endpoints import unavailable
        original=self.get(key,client)
        if original['revision'] != revision: raise ValueError('守护已更新，请刷新后重试')
        if not self.endpoint_vision: return unavailable('NOT_CONFIGURED','首尾图分析未就绪')
        if run and run.get('cameraId') and run['cameraId'] != original['cameraId']:
            raise ValueError('这项守护不属于本轮摄像头范围')
        current=original.get('lastCapture')
        def valid():
            if getattr(self.captures,'hardware_busy',lambda _:False)(original['cameraId']): return False
            latest=self.get(key,client)
            if latest['revision'] != revision or latest['status'] != original['status']: return False
            if latest.get('box') != original.get('box') or latest.get('frame') != original.get('frame'): return False
            if run:
                saved=self.store.run(run['id'])
                if saved and saved.get('status') == 'cancelled': return False
            live=getattr(self.captures.cameras,'live',None)
            session=live.current(original['cameraId']) if live else None
            if session and current and current.get('viewRevision') != session['id']+':'+str(session.get('viewVersion',0)):
                return False
            return True
        live=getattr(self.captures.cameras,'live',None)
        pair=live.recent_pair(original['cameraId'],current['frameId']) if live and current else None
        result=await self.endpoint_vision.analyze(original,current,valid,include_depth=include_depth,flow_pair=pair)
        if not valid(): return unavailable('STALE_CONTEXT','守护或视角已变化，结果已丢弃')
        # Keep private experiment results in the protected cache/run, not the
        # legacy scene listing, and never reschedule observation via save().
        return result

    async def sample_endpoints(self, key, client, revision, *, run=None):
        """Two explicit bounded capture challenges using the existing iOS API.

        Requests cannot make the native decoder run faster. If their real sample
        interval is too wide, DIS is skipped, never resampled/interpolated.
        """
        from ..vision.endpoints import unavailable
        original=self.get(key,client)
        if original['revision']!=revision: raise ValueError('守护已更新')
        if run and run.get('cameraId')!=original['cameraId']: raise ValueError('设备超出本轮范围')
        if not self.endpoint_vision or not self.endpoint_vision.configuration()['ready']:
            return unavailable('NOT_CONFIGURED','图像模型未配置，未请求新画面')
        live=self.captures.cameras.live
        session=live.current(original['cameraId'])
        if not session or session.get('client')!=client:
            return unavailable('LIVE_SESSION_REQUIRED','请在本客户端打开该设备的画面')
        view=(session['id'],session.get('viewVersion',0))
        def valid():
            latest=self.get(key,client)
            saved=self.store.run(run['id']) if run else None
            current=live.current(original['cameraId'])
            return (latest['revision']==revision and latest['status']==original['status']
                    and latest.get('box')==original.get('box') and latest.get('frame')==original.get('frame')
                    and current and current.get('client')==client
                    and (current['id'],current.get('viewVersion',0))==view
                    and not (saved and saved.get('status')=='cancelled')
                    and not getattr(self.captures,'hardware_busy',lambda _:False)(original['cameraId']))
        try:
            captures=[]
            async with asyncio.timeout(12):
                for _ in range(2):
                    if not valid(): return unavailable('STALE_CONTEXT','任务或设备状态已变化')
                    capture=await self.captures.capture(original['cameraId'],purpose='用户请求深度与短间隔画面分析')
                    if capture.get('status')!='completed': return unavailable('CAPTURE_UNAVAILABLE','前台客户端未提供新画面')
                    captures.append(capture)
            pair=live.recent_pair(original['cameraId'],captures[-1]['frameId'])
            # Endpoint comparison still uses the user's target/reference; flow
            # uses the newly captured adjacent pair, with separate source IDs.
            result=await self.endpoint_vision.analyze(original,captures[-1],valid,
                include_depth=True,flow_pair=pair)
            return result if valid() else unavailable('STALE_CONTEXT','分析期间会话或视角已变化，结果已丢弃')
        except asyncio.CancelledError: raise
        except TimeoutError: return unavailable('CAPTURE_TIMEOUT','短时采样超时；没有生成或插值帧')

    def result(self, scene, now=None):
        now = time.time() if now is None else now
        observation = scene['observation']
        def value(state, label, reason): return dict(state=state, label=label, reason=reason)
        if scene['status'] == 'draft': return value('pending', '待确认', scene['reason'])
        if scene['status'] == 'completed': return value('completed', '已提醒 · 已完成', observation['reason'])
        if scene['status'] != 'active': return value('pending', '已暂停', '重新确认后才能继续检查')
        at = observation.get('lastAt')
        if at is None or not -0.5 <= now-at <= self.RESULT_TTL or observation['state'] == 'unknown':
            reason = observation['reason'] if at is None else '最近检查已过期，等待有效新画面'
            label = '无法确认'
            if '重新框选' in reason: label = '请重新框选'
            elif any(text in reason for text in ('会话未就绪', '连接画面', '没有取得新画面', '检查已过期')): label = '等待摄像头画面'
            elif any(text in reason for text in ('建立', '等待新的画面', '等待新画面')): label = '正在识别目标'
            return value('unknown', label, reason)
        desired = 'inside' if scene['plan']['trigger'] == 'enters' else 'outside'
        if observation['state'] != desired:
            return value('confirmed', '最近检查通过', observation['reason'])
        if scene.get('lastAlertAt', 0) > scene.get('lastNormalAt', 0):
            return value('issue', '需要关注', observation['reason'])
        if not observation['armed']:
            reason = ('先把目标放回选框内，识别成功后再移走。' if scene['plan']['trigger'] == 'leaves'
                      else '先保持选框内没有目标，识别成功后再让目标进入。')
            return value('unknown', '等待初始状态', reason)
        return value('checking', '正在确认异常', '发现关注状态，正在按已确认的时长继续检查')

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
            if getattr(self.captures,'hardware_busy',lambda _:False)(scene['cameraId']):
                raise ValueError('设备控制尚未结束或停止结果未知，请先核对后再开启守护。')
            if any(s['status'] == 'active' and s['cameraId'] == scene['cameraId'] for s in self.list_all()):
                raise ValueError('这台摄像头已有运行中的自定义场景，请先暂停它。')
            scene.update(status='active', revision=revision+1, confirmedRevision=revision,
                         observation=self.empty_observation('已开启，等待建立新观察基线'), reason='已开启，等待新的画面',
                         healthSince=time.time(), healthNotified=False, lastAlertAt=0, lastNormalAt=0,
                         validatedViewRevision=scene['frame'].get('viewRevision'))
            self.save(scene, time.time())
        return scene

    def pause(self, key, client, revision):
        with self.store.transaction():
            scene = self.get(key, client)
            if scene['revision'] != revision: raise ValueError('任务已更新，请刷新。')
            if scene['status'] not in {'active', 'paused'}: raise ValueError('这项场景没有运行。')
            scene.update(status='draft', revision=revision+1, stage='select', frame=None, box=None,
                         reason='已暂停；再次开启前需要重新取图和框选', observation=self.empty_observation('已暂停'))
            scene.pop('lastCapture',None); scene.pop('endpointAnalysis',None)
            self.save(scene)
        return scene

    @staticmethod
    def is_reconnection(previous, current):
        # A new native session starts at view version zero. An explicit control
        # in the same session changes the view and still requires re-selection.
        if not isinstance(previous, str) or not isinstance(current, str): return False
        old, sep1, _ = previous.rpartition(':')
        new, sep2, version = current.rpartition(':')
        return bool(sep1 and sep2 and old.startswith('live-') and new.startswith('live-') and old != new and version == '0')

    async def step(self, now=None):
        now = time.time() if now is None else now
        async with self.worker_lock:
            with self.store.transaction():
                row = self.store.db.execute("SELECT payload FROM visual_scenes WHERE due<=? AND json_extract(payload,'$.status')='active' ORDER BY due LIMIT 1", (now,)).fetchone()
                if not row: return False
                original = json.loads(row[0]); self.save(original, now + self.PERIOD)
            with GuardRun(self.store, original) as audit:
                return await self._observe_once(original, audit)

    async def _observe_once(self, original, audit):
        # Keep observation and commit gates unchanged; telemetry only reads
        # the values already produced by this one scheduled check.
        receipt = None; reconnected = False; observation_started = False
        capture_started = time.monotonic()
        event('capture', status='started')
        try:
            receipt = await self.captures.capture(original['cameraId'], purpose='用户开启的自定义场景观察')
            event('capture', status='completed' if receipt.get('status')=='completed' else 'unavailable',
                  duration=round((time.monotonic()-capture_started)*1000, 2),
                  frame=frame_reference(receipt))
            self.validate_frame(receipt)
            previous = original.get('validatedViewRevision') or original['frame'].get('viewRevision')
            current = receipt.get('viewRevision')
            reconnected = self.is_reconnection(previous, current)
            if current != previous and not reconnected:
                raise SceneUnavailable('摄像头视角已变化，请暂停并重新框选。')
            observation_started = True
            result = Judgment.model_validate(await self.harness.observe(original, receipt, self.store)).model_dump()
            if reconnected and not result['viewMatchesReference']:
                raise SceneUnavailable('重连后无法确认选框仍对应原区域，请检查画面并重新框选。')
            if not result['regionClear'] or (result['state']=='inside' and not result['identityClear']): result['state']='unknown'
        except asyncio.CancelledError:
            if receipt is None: event('capture', status='cancelled')
            raise
        except Exception as error:
            if receipt is None: event('capture', status='failed', errorType=type(error).__name__)
            if not observation_started:
                event('preprocessing', status='skipped', code='CAPTURE_UNAVAILABLE' if receipt is None else 'FRAME_REJECTED',
                      depth={'status':'skipped'}, flow={'status':'skipped'})
            event('unavailable', status='failed', errorType=type(error).__name__,
                  frame=frame_reference(receipt), stage='capture' if receipt is None else 'validation_or_observation')
            result = dict(state='unknown', reason=str(error) if isinstance(error, SceneUnavailable) else '观察暂未完成，等待新画面')
        with self.store.transaction():
            scene = self.get(original['id'], original['clientId'])
            if scene['revision'] != original['revision'] or scene['status'] != 'active':
                audit.finish(disposition='discarded', code='SCENE_CHANGED', judgment=result,
                             currentRevision=scene['revision'], sceneStatus=scene['status'])
                return True
            if receipt and receipt.get('status') == 'completed':
                scene['lastCapture'] = receipt
            if reconnected and result.get('viewMatchesReference'):
                scene.update(validatedViewRevision=receipt['viewRevision'], observation=self.empty_observation('重连后已核对视角，重新建立观察基线'))
            alert = self.advance(scene, result, receipt, time.time())
            scene['lastGuardRunId'] = audit.id
            if alert: self.publish(scene, receipt)
            self.check_health(scene, time.time())
            self.save(scene, time.time() + self.PERIOD)
        audit.finish(disposition='committed', judgment=result, observation=scene['observation'],
                     resultState=self.result(scene, time.time())['state'], alertPublished=bool(alert),
                     evidenceId=scene['evidenceIds'][-1] if alert else None)
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
            scene['lastNormalAt'] = observed
        elif current['armed']:
            current.update(since=old['since'] if old['since'] is not None else observed, count=old['count']+1)
        scene['observation'] = current
        if current['armed'] and current['count'] >= 2 and observed-current['since'] >= plan['confirmationSeconds']:
            current.update(armed=False, since=None, count=0)
            scene['lastAlertAt'] = observed
            if plan['completion'] == 'once': scene['status'] = 'completed'
            return True
        return False

    def check_health(self, scene, now):
        """One actionable, installation-scoped notice per unresolved gap."""
        result = self.result(scene, now)
        if scene['status'] != 'active' or result['state'] != 'unknown':
            scene.update(healthSince=None, healthNotified=False)
            return
        if scene.get('healthSince') is None: scene['healthSince'] = now
        if now-scene['healthSince'] < self.HEALTH_GRACE or scene.get('healthNotified'): return
        preferences = self.proactive.personal.profile(scene['clientId'])['preferences']
        if not preferences['enabled'] or self.proactive.quiet(preferences, now): return
        key = 'scene-health-' + uuid.uuid4().hex
        message = dict(id='message-'+key, jobId=key, runId=None, role='assistant', origin='proactive',
                       kind='visual_scene', title=scene['plan']['title']+'需要检查',
                       body=scene['plan']['title']+'：持续无法确认。'+result['reason']+'。请打开 App 检查摄像头画面和 Skill 条件；这不代表已发生异常事件。',
                       why='已开启的 Skill 持续缺少有效判断',
                       sources=[dict(id='camera:'+scene['cameraId'], type='camera', cameraId=scene['cameraId'])],
                       createdAt=now, read=False, feedback=None, skillId=None, triggerKey=key,
                       delivery='in_app', valueScore=None)
        encoded = json.dumps(message, ensure_ascii=False)
        self.store.db.execute('INSERT INTO assistant_messages VALUES (?,?,?,?,?)', (message['id'],scene['clientId'],key,now,encoded))
        self.store.db.execute('INSERT INTO personal_inbox VALUES (?,?,?,?)', (message['id'],scene['clientId'],key,encoded))
        if self.proactive.push: self.proactive.push.message(scene['clientId'], message, {'expiresAt':now+3600})
        scene['healthNotified'] = True

    def publish(self, scene, receipt):
        key = 'scene-evidence-' + uuid.uuid4().hex
        at = receipt.get('capturedAt') or receipt['sampledAt']
        evidence = dict(id=key, skillId='', cameraId=scene['cameraId'], capturedAt=at,
                        relation=scene['observation']['state'], reason=scene['observation']['reason'],
                        imageUrl=receipt['imageUrl'], revision=scene['revision'], sourceType=receipt['sourceType'],
                        sceneId=scene['id'], frameId=receipt['frameId'], timestampMeaning=receipt['timestampMeaning'],
                        guardRunId=scene.get('lastGuardRunId'))
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
