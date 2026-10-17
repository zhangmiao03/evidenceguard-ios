"""Single-team product gateway. Roles are assigned by the host, never model JSON.

Official credentials stay in the foreground SDK host. Executor credentials are
bound to one installation and device; SDK discovery remains client-reported.
The existing live challenge/decoder is the ONLY source of observation images.
"""
import asyncio
import base64
import hashlib
import hmac
import json
import secrets
import time
from io import BytesIO
from PIL import Image

from .vendor.camera_tools.catalog import TOOLS, FIELDS, ToolError
from .vendor.camera_tools.runtime import Runtime, require

TEAM = 'product'
PLATFORMS = {'ios': 'iOS', 'web': 'Web', 'android': 'Android'}
NATIVE = {'device_state_get', 'device_settings_get', 'device_settings_set',
          'camera_set_night_vision', 'camera_events_query', 'camera_event_get',
          'camera_ptz_step', 'camera_presets_list', 'camera_goto_preset',
          'camera_light_set', 'doorbell_light_set', 'camera_dual_mode_set',
          'doorbell_replies_list', 'doorbell_reply_play'}
MOVEMENT = {'camera_ptz_step', 'camera_goto_preset', 'camera_dual_mode_set'}
IMPLEMENTED_FIELDS = {'ptzSpeed', 'microphoneEnabled', 'audioRecordEnabled', 'statusLED'}
TERMINAL = {'completed', 'failed', 'cancelled'}


def public(value):
    if isinstance(value, list): return [public(v) for v in value]
    if isinstance(value, dict):
        return {k: public(v) for k, v in value.items() if k not in {
            'leaseToken', 'resolvedReferences', 'idempotencyRecord', 'vendorHandle', 'tokenHash', 'token'}}
    return value


class HardwareGateway:
    def __init__(self, store, cameras, captures, path):
        self.store, self.cameras, self.captures = store, cameras, captures
        self.runtime = Runtime(path, [], policy='competition')
        self.hosts = {h['id']: h for h in self.runtime.store.all('host', TEAM)}
        self.observations = {}
        self.scenes = None
        self.visual_control = None
        # A process restart never certifies a foreground client is still present.
        with self.runtime.store.transaction():
            for host in self.hosts.values():
                host['active'] = False
                self.runtime.store.put('host', host)
            for op in self.runtime.store.all('operation', TEAM):
                if op['executionState'] not in TERMINAL:
                    op['executionState'] = 'unknown' if op['dispatchState'] != 'not_sent' else 'cancelled'
                    self.runtime.store.put('operation', op)
        captures.hardware_busy = self.busy

    def devices(self):
        return {d['id']: d for d in [*self.cameras.sdk_ingest.devices(), *self.cameras.live.records()]}

    def principal(self, role, identity, devices=None, task=None):
        ids = list(devices if devices is not None else self.devices())
        tasks = [task] if task else sorted({f'device:{d}' for d in ids} |
            {o['taskId'] for o in self.runtime.store.all('operation', TEAM) if o['deviceId'] in ids})
        p = dict(id=identity, team=TEAM, role=role, devices=ids, tasks=tasks,
                 allowedExecutorPlatforms=list(PLATFORMS.values()))
        # Keep the original immutable request scope available for dispatch rechecks.
        self.runtime.principals[:] = [v for v in self.runtime.principals if v['id'] != identity] + [p]
        return p

    def human(self, client): return self.principal('human', 'human:' + client)

    def guarded(self, device):
        return bool(self.store.owner(device) or (self.scenes and any(
            s['cameraId'] == device and s['status'] == 'active' for s in self.scenes.list_all())))

    def busy(self, device):
        self.runtime._expire(TEAM)
        return any(o['deviceId'] == device and o['control'] and o['executionState'] in {'executing', 'verifying', 'unknown'}
                   and not o.get('leaseReleasedByHuman') for o in self.runtime.store.all('operation', TEAM))

    def register(self, client, body):
        device = self.devices().get(body['deviceId'])
        require(device and device['model'] == body['model'], 'DEVICE_NOT_REGISTERED', '先同步同一官方设备身份')
        platform = PLATFORMS[body['platform']]
        if platform == 'Web':
            session = self.cameras.live.authorize(body['sessionId'], client, body['mediaToken'])
            require(session['deviceId'] == device['id'] and session['platform'] == 'web', 'SESSION_MISMATCH', '直播会话不匹配')
            require(body['privacy'] == 'unknown', 'UNSUPPORTED_PARAMETER', 'Web SDK 未提供隐私回读，不能自行声明已关闭')
        routes = body['routes']
        allowed = {'camera_observe'} | (NATIVE if platform != 'Web' else set())
        require(set(routes) <= allowed, 'UNSUPPORTED_ROUTE', '不能登记尚未接入的执行路线')
        require(set(body.get('fields', {})) <= IMPLEMENTED_FIELDS, 'UNSUPPORTED_FIELD', '设置字段尚未实现')
        eid = 'executor-' + hashlib.sha256((client + ':' + device['id'] + ':' + platform).encode()).hexdigest()[:24]
        token = secrets.token_urlsafe(32)
        p = self.principal('executor', eid, [device['id']]); p['platform'] = platform
        old_host = self.hosts.get(eid)
        if old_host:
            self.disconnect(p, old_host)
        self.runtime.register(p, dict(platform=platform, simulated=False, adapterVersion=body['adapterVersion'],
            sdkVersion=body.get('sdkVersion','unknown'),
            sdkArtifactHash=body['sdkArtifactHash'], devices=[dict(deviceId=device['id'], model=device['model'],
                label=device['name'], firmwareVersion=body['firmwareVersion'], routes=routes,
                fields=body.get('fields', {}), privacy=body['privacy'], officialIdentityReady=body['officialIdentityReady'])]))
        host = dict(id=eid, team=TEAM, client=client, platform=platform, deviceId=device['id'], active=True,
                    tokenHash=hashlib.sha256(token.encode()).hexdigest(), sessionId=body.get('sessionId'))
        with self.runtime.store.transaction(): self.runtime.store.put('host', host)
        self.hosts[eid] = host
        with self.runtime.store.transaction():
            d = self.runtime.device(p, device['id'])
            if not body['firmwareVersion'].strip() or body['firmwareVersion'].strip().lower() == 'unknown':
                # With no firmware readback, a reconnect cannot reuse old proof.
                d['capabilityRevision'] = hashlib.sha256((d['capabilityRevision'] + ':' + secrets.token_hex(16)).encode()).hexdigest()
            d['viewRevision'] += 1
            d['privacySource'] = 'sdk' if platform != 'Web' else 'unknown'
            self.runtime.store.put('device', d)
        return dict(executorId=eid, token=token, deviceId=device['id'])

    def executor(self, client, eid, token):
        host = self.hosts.get(eid)
        require(host and host['active'] and host['client'] == client and
                hmac.compare_digest(host['tokenHash'], hashlib.sha256(token.encode()).hexdigest()),
                'EXECUTOR_UNAUTHORIZED', '执行会话已结束或不属于此客户端', 403)
        if host['platform'] == 'Web':
            s = self.cameras.live.current(host['deviceId'])
            require(s and s['id'] == host['sessionId'] and s['client'] == client,
                    'EXECUTOR_UNAVAILABLE', '先打开此设备的当前直播')
        p = self.principal('executor', eid, [host['deviceId']]); p['platform'] = host['platform']
        return p, host

    def snapshot(self, client):
        p = self.human(client)
        result = public(self.runtime.snapshot(p))
        for d in result['devices']:
            host = self.hosts.get(d['executorId'], {})
            executor = self.runtime.store.get('executor', d['executorId'])
            d['executorOnline'] = bool(host.get('active') and time.time() - executor['lastSeen'] < 30)
            d['validationResults'] = [v for v in self.runtime.store.all('validation', TEAM)
                                      if v['deviceId'] == d['id'] and v['capabilityRevision'] == d['capabilityRevision']]
        return result

    def invoke(self, p, name, arguments, task, key, platform, diagnostic=False):
        if name == 'camera_evidence_get':
            ref = self.runtime.record(p,'ref',arguments['mediaRef'])
            require(ref['kind'] == 'media' and ref.get('source') == 'executor_upload', 'UNSUPPORTED_ROUTE','录像下载执行器尚未接入')
            require(ref['validUntil'] > time.time() and ref['taskId'] == task,'STALE_REFERENCE','媒体引用过期或超出当前任务')
            source = self.runtime.record(p,'operation',ref['operationId'])
            capture = source.get('result',{}).get('data',{}).get('capture')
            require(capture,'UNSUPPORTED_ROUTE','该引用没有已保存的产品证据')
            return {'capture':capture,'readPath':capture['imageUrl'],'authorization':'product_team_auth'}
        device = arguments.get('deviceId')
        if device:
            d = self.runtime.device(p, device)
            if name == 'camera_observe' and d['executorPlatform'] == 'Web':
                require(diagnostic and p['role'] == 'human' and d.get('privacyCheckedUntil',0) > time.time(),
                        'PRIVACY_UNCONFIRMED', 'Web 工具取样需本会话人工核对隐私；Agent 可使用现有直播取帧工具')
        if name in TOOLS and TOOLS[name]['control']:
            require(not self.guarded(arguments.get('deviceId')), 'ACTIVE_SKILL', '先暂停这台设备的守护任务，再调整设备')
        op = self.runtime.invoke(p, name, arguments, dict(taskId=task, idempotencyKey=key,
            requestedPlatform=platform, diagnostic=diagnostic))
        return public(op)

    def call(self, client, body):
        p = self.human(client)
        # Product control panel has a stable device scope; Agent scopes are host-owned.
        device = body['arguments'].get('deviceId')
        if not device:
            for key in ('operationId', 'eventRef', 'mediaRef'):
                if key in body['arguments']:
                    record = self.runtime.record(p, 'operation' if key == 'operationId' else 'ref', body['arguments'][key])
                    device = record['deviceId']; break
        task = body.get('taskId') or (f'device:{device}' if device else next(iter(p['tasks']), 'no-device'))
        require(task in p['tasks'], 'PERMISSION_DENIED', '任务范围不属于当前工作区', 403)
        result = self.invoke(p, body['name'], body['arguments'], task, body['idempotencyKey'],
                             PLATFORMS[body['platform']], body.get('diagnostic', False))
        if result.get('executionState'): return self.sync_run(self.runtime.record(p,'operation',result['id']))
        return result

    async def claim(self, p, host):
        # Do not dispatch controls during a fresh-frame capture or another client's live view.
        device = host['deviceId']
        live = self.cameras.live.current(device)
        blocked = self.captures.gate(device).locked() or bool(live and live['client'] != host['client'])
        # Revoking a task owner after approval must still block dispatch.
        if self.guarded(device):
            with self.runtime.store.transaction():
                for op in self.runtime.store.all('operation', TEAM):
                    if op['deviceId'] == device and op['control'] and op['executionState'] == 'queued':
                        op.update(executionState='failed', error={'code':'ACTIVE_SKILL','message':'守护任务占用设备'})
                        self.runtime.store.put('operation', op)
        return self.runtime.claim(p, allow_new=not blocked)

    async def observe(self, p, host, body):
        op = self.runtime.record(p, 'operation', body['operationId'])
        require(op['tool'] == 'camera_observe' and op['executorId'] == p['id'] and
                op.get('leaseToken') == body['leaseToken'],
                'INVALID_STATE', '当前操作不是本执行器的新帧请求')
        if op['executionState'] in TERMINAL: return public(op)
        require(op['executionState'] == 'executing', 'INVALID_STATE', '已失去执行窗口，不能重复采集')
        if op['id'] not in self.observations:
            task = asyncio.create_task(self._observe(p, host, body, op))
            self.observations[op['id']] = task
            task.add_done_callback(lambda _: self.observations.pop(op['id'], None))
        return await asyncio.shield(self.observations[op['id']])

    async def _observe(self, p, host, body, op):
        try:
            return await self._capture_observation(p, host, body, op)
        except Exception as error:
            latest = self.runtime.record(p, 'operation', op['id'])
            if latest['executionState'] in TERMINAL: return public(latest)
            return self.sync_run(self.runtime.finish(p, op['id'], dict(leaseToken=body['leaseToken'], simulated=False,
                sdkUsed=False, status='failed', error={'code':error.code if isinstance(error, ToolError) else 'CAPTURE_UNAVAILABLE',
                'message':'缺少可核验的解码新帧，不能用于控制参考' if isinstance(error, ToolError) else '未取得可核验的新帧，请检查执行端直播'})))

    async def _capture_observation(self, p, host, body, op):
        live = self.cameras.live.current(host['deviceId'])
        require(live and live['client'] == host['client'] and PLATFORMS[live['platform']] == host['platform'],
                'LIVE_REQUIRED', '请在执行端前台打开这台设备的直播')
        owner = self.store.owner(host['deviceId'])
        capture = await self.captures.capture(host['deviceId'], owner['id'] if owner else None, '硬件工具请求新画面')
        if capture['status'] != 'completed':
            return self.sync_run(self.runtime.finish(p, op['id'], dict(leaseToken=body['leaseToken'], simulated=False,
                sdkUsed=False, status='failed', error={'code':'CAPTURE_UNAVAILABLE','message':capture['reason']})))
        raw, mime, stored = self.store.media(capture['mediaId'])
        # Do not manufacture decoder progress from HTTP sequence or SDK bitrate.
        # Existing clients still supply readable samples, but cannot turn them
        # into v0.3 control references without a genuine decoded-frame receipt.
        frame = stored['frame'].get('decoder_frame')
        from .vendor.camera_tools.verification import check_frame
        check_frame(frame, host['deviceId'], time.time()*1000)
        with Image.open(BytesIO(raw)) as image:
            dimensions = list(image.size)
        require(dimensions == frame['dimensions'], 'STALE_FRAME', '解码帧与图片尺寸不一致')
        if len(raw) > 2 * 1024 * 1024:
            with Image.open(BytesIO(raw)) as image:
                image = image.convert('RGB')
                output = BytesIO(); image.save(output,format='JPEG',quality=80)
                raw, mime = output.getvalue(), 'image/jpeg'
        latest = self.runtime.record(p, 'operation', op['id'])
        if latest['executionState'] != 'executing' or latest.get('stopRequested'): return public(latest)
        # This is a validated product frame, never a user-selected image or arbitrary URL.
        media = self.runtime.register_media(p, dict(operationId=op['id'], leaseToken=body['leaseToken'],
            mimeType=mime, sha256=hashlib.sha256(raw).hexdigest(), base64=base64.b64encode(raw).decode()))
        result = self.runtime.finish(p, op['id'], dict(leaseToken=body['leaseToken'], simulated=False,
            status='acknowledged', sdkUsed=True, sdkAccepted=None, sdkResult={'source':'product_live_challenge'}, data={'capture':capture},
            references=[dict(kind='observation', label='本次请求后的直播取样', mediaRef=media['id'],
                source='decoded_live_frame', dimensions=dimensions, frame=frame,
                sourceTimestamp=None, sourceTimeKind='client_decode')]))
        return self.sync_run(result)

    def finish(self, p, body):
        before = self.runtime.record(p, 'operation', body['operationId'])
        if before['tool'] == 'camera_observe':
            if before['executionState'] in TERMINAL: return public(before)
            require(body['status'] != 'acknowledged', 'UNSUPPORTED_ROUTE', '观察只能来自产品新帧校验链路')
        op = self.runtime.finish(p, body['operationId'], body)
        if op['tool'] == 'device_state_get' and body['status'] == 'acknowledged':
            state = body.get('data',{}).get('privacy','unknown')
            with self.runtime.store.transaction():
                d=self.runtime.device(p,op['deviceId']); d['privacy']=state if state in {'on','off'} else 'unknown'
                self.runtime.store.put('device',d)
        if op['tool'] in MOVEMENT and not op.get('productViewInvalidated'):
            self.cameras.live.invalidate_view(op['deviceId'])
            with self.runtime.store.transaction():
                d = self.runtime.device(p,op['deviceId'])
                if not op.get('viewInvalidated'): d['viewRevision'] += 1
                d['viewConfirmationRequired'] = True
                self.runtime.store.put('device',d)
                op['productViewInvalidated'] = True; self.runtime.store.put('operation',op)
        value=self.sync_run(op)
        if self.visual_control and op['tool'] in MOVEMENT:
            self.visual_control.operation_finished(op)
        return value

    def sync_run(self, op):
        value=public(op)
        if op.get('principalId','').startswith('agent:'):
            run=self.store.run(op['principalId'][6:])
            if run:
                operations=run.setdefault('hardwareOperations',[])
                operations[:]=[o for o in operations if o['id']!=op['id']]+[value]
                self.store.save_run(run)
                self.store.event(run['id'],'hardware_operation',{'operationId':op['id'],'deviceId':op['deviceId'],
                    'tool':op['tool'],'executorPlatform':op['executorPlatform'],'state':op['executionState'],
                    'capabilityRevision':op['capabilityRevision']})
        return value

    def attach_tools(self, registry, skill_id, camera_id, run):
        if not run or not self.runtime.store.all('device', TEAM): return
        devices=self.store.skill(skill_id)['devices'] if skill_id else ([camera_id] if camera_id else list(self.devices()))
        task='skill:'+skill_id if skill_id else 'conversation:'+run['conversationId']
        p=self.principal('agent','agent:'+run['id'],devices,task)
        for spec in self.runtime.tools(p):
            name=spec['name']
            if name == 'camera_observe' and not any(d['id'] in devices and d['executorPlatform'] != 'Web'
                    for d in self.runtime.store.all('device',TEAM)): continue
            async def invoke(_name=name,**arguments):
                try:
                    # Stable for a repeated identical call within a run; no model-generated retry keys.
                    key=hashlib.sha256(json.dumps([run['id'],_name,arguments],sort_keys=True).encode()).hexdigest()
                    return await self.agent_call(_name,arguments,task=task,devices=devices,key=key,run_id=run['id'],client_platform=run.get('clientPlatform'))
                except ToolError as error: raise ValueError(error.code+': '+error.message) from error
            registry.register_json(name,invoke,spec['inputSchema'],spec['description'])

    def release(self, client, device):
        p = self.human(client); d = self.runtime.device(p, device)
        host = self.hosts.get(d['executorId'], {})
        # Explicit handoff only: the owning client, or a human after its heartbeat expires.
        e = self.runtime.store.get('executor', d['executorId'])
        require(host.get('client') == client or time.time() - e['lastSeen'] >= 30,
                'RESOURCE_BUSY', '请先在原执行端停止，或等其离线后明确释放')
        pending = [o for o in self.runtime.store.all('operation', TEAM) if o['deviceId'] == device and
                   o['executionState'] not in TERMINAL and not o.get('leaseReleasedByHuman')]
        require(not pending, 'RESOURCE_BUSY', '先取消待执行操作；已发出或未知操作须停止并核对')
        require(self.cameras.live.current(device) is None, 'RESOURCE_BUSY', '先停止原直播会话')
        with self.runtime.store.transaction():
            host['active'] = False; self.runtime.store.put('host', host)
            # References/validations cannot survive an explicit host handoff.
            for kind in ('ref','validation'):
                for record in self.runtime.store.all(kind,TEAM):
                    if record['deviceId'] == device:
                        self.runtime.store.db.execute('DELETE FROM records WHERE kind=? AND id=?',(kind,record['id']))
            self.runtime.store.db.execute("DELETE FROM records WHERE kind='device' AND id=?", (device,))
        return {'status':'released'}

    def disconnect(self, p, host):
        with self.runtime.store.transaction():
            for op in self.runtime.store.all('operation', TEAM):
                if op['executorId'] == p['id'] and op['executionState'] not in TERMINAL:
                    op['executionState'] = 'cancelled' if op['dispatchState'] == 'not_sent' else 'unknown'
                    self.runtime.store.put('operation', op)
            host['active'] = False; self.runtime.store.put('host', host)
            e = self.runtime.store.get('executor', p['id']); e['lastSeen'] = 0; self.runtime.store.put('executor', e)
        return {'status':'disconnected'}

    def attest_privacy(self, client, device, evidence):
        p = self.human(client); d = self.runtime.device(p,device)
        host = self.hosts.get(d['executorId'],{})
        require(host.get('client') == client and host.get('active') and host.get('platform') == 'Web',
                'PERMISSION_DENIED','只能在当前 Web 直播执行端人工核对',403)
        live = self.cameras.live.current(device)
        require(live and live['id'] == host['sessionId'], 'LIVE_REQUIRED','直播会话已结束')
        with self.runtime.store.transaction():
            now = time.time()
            d.update(privacy='off',privacySource='human_diagnostic',privacyCheckedUntil=now+300,
                     privacyCheck=dict(evidence=evidence,reviewedBy=p['id'],at=now,sessionId=live['id']))
            self.runtime.store.put('device',d)
            self.runtime.store.audit(p,'privacy.manually_checked',device)
        return {'status':'recorded','scope':'human_diagnostic_only','validForSeconds':300}

    def cancel_run(self, run_id):
        for op in self.runtime.store.all('operation',TEAM):
            if op['principalId'] == 'agent:'+run_id and op['executionState'] not in TERMINAL:
                p=self.principal('agent','agent:'+run_id,[op['deviceId']],op['taskId'])
                self.sync_run(self.runtime.invoke(p,'camera_stop',{'operationId':op['id']},dict(
                    taskId=op['taskId'],idempotencyKey='cancel:'+op['id'],requestedPlatform='Web')))

    async def agent_call(self, name, arguments, *, task, devices, key, run_id, client_platform=None):
        p = self.principal('agent', 'agent:' + run_id, devices, task)
        result = self.invoke(p, name, arguments, task, key, PLATFORMS.get(client_platform,'Web'))
        if result.get('id', '').startswith('op_'):
            with self.runtime.store.transaction():
                op=self.runtime.record(p,'operation',result['id'])
                op['requesterPlatform']=PLATFORMS.get(client_platform,'unknown')
                self.runtime.store.put('operation',op)
            result=public(op)
            # Read tools can wait briefly. Controls always return a concrete confirmation card.
            if not result['control']:
                for _ in range(90):
                    result = public(self.runtime.record(p, 'operation', result['id']))
                    if result['executionState'] in TERMINAL | {'unknown'}: break
                    await asyncio.sleep(.1)
            result['runId'] = run_id
        return result

    async def close(self):
        tasks=list(self.observations.values())
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        self.runtime.store.db.close()
