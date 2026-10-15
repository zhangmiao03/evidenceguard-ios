"""Single-team native/browser SDK relay. Video stays on the official media path.

Only a response to a server-issued capture challenge can become a new Agent
observation. Device capture time is deliberately unknown: these SDKs expose a
client-side sample, not an attested sensor timestamp. Sessions are ephemeral;
after restart every device needs a new foreground executor.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import io
import json
import secrets
import time
import uuid
from dataclasses import asdict
from typing import Literal

from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field

from .contracts import CapabilityState, Channel, DeviceManifest, FrameRef, SnapshotKind, SnapshotReceipt
from ..ops import CTX


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ImportedDevice(Input):
    sn: str = Field(pattern=r'^T(8171|8214)[A-Z0-9]{3,27}$')
    model: Literal['T8171', 'T8214']
    name: str = Field(min_length=1, max_length=80)


class DeviceImport(Input):
    accountId: str = Field(min_length=1, max_length=160)
    environment: Literal['PR', 'QA'] = 'PR'
    platform: Literal['ios', 'web', 'android']
    devices: list[ImportedDevice] = Field(min_length=1, max_length=100)


class SessionStart(Input):
    deviceId: str = Field(min_length=1, max_length=100)
    platform: Literal['ios', 'web', 'android']


class Heartbeat(Input):
    state: Literal['connecting', 'streaming', 'stopped', 'failed']
    sequence: int = Field(ge=0)
    frameAgeMs: int | None = Field(default=None, ge=0, le=86400000)


class FrameUpload(Input):
    requestId: str = Field(max_length=100)
    sequence: int = Field(gt=0)
    channelId: Literal['main'] = 'main'
    imageBase64: str = Field(min_length=1, max_length=7_000_000)
    width: int = Field(gt=0, le=8192)
    height: int = Field(gt=0, le=8192)
    sampledAt: float = Field(gt=0, allow_inf_nan=False)


class CaptureRequest(Input):
    purpose: str = Field(default='查看当前画面', min_length=1, max_length=120)


class LiveDevices:
    heartbeat_ttl = 12
    frame_ttl_ms = 4000

    def __init__(self, store):
        self.store = store
        self.sessions: dict[str, dict] = {}
        self.pending: dict[str, dict] = {}
        self.frames: dict[str, tuple] = {}
        with store.transaction():
            store.db.execute('CREATE TABLE IF NOT EXISTS live_devices (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')

    def records(self):
        with self.store.lock:
            rows = self.store.db.execute('SELECT payload FROM live_devices ORDER BY id').fetchall()
        return [json.loads(row[0]) for row in rows]

    def record(self, device_id):
        with self.store.lock:
            row = self.store.db.execute('SELECT payload FROM live_devices WHERE id=?', (device_id,)).fetchone()
        if not row:
            raise KeyError(device_id)
        return json.loads(row[0])

    def import_devices(self, body: DeviceImport, client: str):
        # The current service is a trusted single-team workspace, not a vendor
        # ownership verifier. Persist provenance; never infer device binding.
        account = hashlib.sha256((body.environment + ':' + body.accountId).encode()).hexdigest()
        result = []
        with self.store.transaction():
            for item in body.devices:
                if not item.sn.startswith(item.model):
                    raise ValueError('设备型号与序列号不匹配')
                device_id = 'sdk-' + hashlib.sha256(item.sn.encode()).hexdigest()[:20]
                old = next((d for d in self.records() if d['id'] == device_id), None)
                if old and old['accountFingerprint'] != account:
                    raise ValueError('此设备已有不同官方账号/环境的记录，请先由管理员核对授权；没有自动合并')
                record = dict(id=device_id, sn=item.sn, model=item.model, name=item.name,
                              accountFingerprint=account, environment=body.environment,
                              importedBy=client, platform=body.platform, importedAt=time.time(),
                              registrationSource='client_reported_sdk_discovery' if body.platform == 'ios' else 'client_supplied_sn',
                              ownershipVerified=False)
                if old:
                    record['importedAt'] = old['importedAt']
                self.store.db.execute('INSERT OR REPLACE INTO live_devices VALUES (?,?)',
                                      (device_id, json.dumps(record, ensure_ascii=False)))
                result.append(record)
        return result

    def current(self, device_id):
        now = time.time()
        return next((s for s in self.sessions.values() if s['deviceId'] == device_id
                     and s['state'] not in {'stopped', 'failed'}
                     and now - s['heartbeatAt'] <= self.heartbeat_ttl), None)

    def ready(self, session):
        return bool(session and session['state'] == 'streaming' and session['sequence'] > 0
                    and session.get('frameAgeMs') is not None
                    and session['frameAgeMs'] + (time.time() - session['heartbeatAt']) * 1000 <= self.frame_ttl_ms)

    def start(self, body: SessionStart, client):
        self.record(body.deviceId)
        self.expire()
        if self.current(body.deviceId):
            raise ValueError('此设备已有画面采集会话，请先在原客户端停止，或等待离线会话过期')
        sid, token = 'live-' + uuid.uuid4().hex, secrets.token_urlsafe(32)
        self.sessions[sid] = dict(id=sid, deviceId=body.deviceId, platform=body.platform,
                                  client=client, tokenHash=hashlib.sha256(token.encode()).hexdigest(),
                                  state='connecting', sequence=0, heartbeatAt=time.time(), frameAgeMs=None)
        self.observe('session.started', self.sessions[sid])
        return dict(id=sid, deviceId=body.deviceId, token=token, heartbeatTTL=self.heartbeat_ttl, traceId=CTX.get().get('traceId'))

    def observe(self, name, session, **details):
        if getattr(self.store, 'ops', None):
            self.store.ops.emit(name,data=dict(deviceId=session['deviceId'],sessionId=session['id'],
                executor=session['platform'],state=session['state'],**details))

    def authorize(self, sid, client, token):
        s = self.sessions.get(sid)
        if not s or s['client'] != client or not hmac.compare_digest(s['tokenHash'], hashlib.sha256(token.encode()).hexdigest()):
            raise KeyError('media session')
        if time.time() - s['heartbeatAt'] > self.heartbeat_ttl or s['state'] in {'stopped', 'failed'}:
            raise ValueError('媒体会话已结束或过期，请重新开流')
        return s

    def heartbeat(self, s, body: Heartbeat):
        if body.sequence < s['sequence']:
            raise ValueError('拒绝旧的媒体心跳')
        changed=s['state']!=body.state
        s.update(state=body.state, sequence=body.sequence, frameAgeMs=body.frameAgeMs, heartbeatAt=time.time())
        if changed: self.observe('session.state_changed',s)
        if body.state in {'stopped', 'failed'}:
            self.stop(s)
        return dict(status=s['state'], ready=self.ready(s))

    def stop(self, s):
        if s['state']!='stopped': self.observe('session.stopped',s)
        s['state'] = 'stopped'
        for p in list(self.pending.values()):
            if p['sessionId'] == s['id'] and not p['future'].done():
                p['future'].set_exception(ValueError('采集客户端已停止直播'))

    def expire(self):
        now = time.time()
        for sid, s in list(self.sessions.items()):
            if now - s['heartbeatAt'] > self.heartbeat_ttl:
                self.observe('session.expired',s)
                self.stop(s)
                del self.sessions[sid]
        for fid, (frame, _, _) in list(self.frames.items()):
            if now - frame.received_at > 30:
                del self.frames[fid]

    def commands(self, s):
        self.expire()
        return [dict(requestId=rid, sessionId=p['sessionId'], deviceId=p['deviceId'],
                     afterSequence=p['afterSequence'], deadline=p['deadline'], channelId='main',
                     traceId=p.get('trace',{}).get('traceId'),parentSpanId=p.get('trace',{}).get('spanId'))
                for rid, p in self.pending.items() if p['sessionId'] == s['id']
                and not p['future'].done() and p['deadline'] > time.time()]

    def invalidate_view(self, device_id):
        s=self.current(device_id)
        if s:
            s['viewVersion']=s.get('viewVersion',0)+1
            s.pop('lastFrameUrl',None)
            s['frameAgeMs']=None
        for pending in self.pending.values():
            if pending['deviceId']==device_id and not pending['future'].done():
                pending['future'].set_exception(ValueError('设备视角已改变，需要重新请求新画面'))

    def upload(self, s, body: FrameUpload):
        p = self.pending.get(body.requestId)
        if not p or p['sessionId'] != s['id'] or p['deviceId'] != s['deviceId']:
            raise ValueError('没有匹配的新画面请求，拒绝缓存图片或其他设备的回执')
        if p['future'].done() or p['deadline'] < time.time():
            raise ValueError('画面请求已完成或过期')
        if not self.ready(s) or body.sequence <= p['afterSequence']:
            raise ValueError('需要请求发出后的新直播取样，不能返回旧帧')
        try:
            raw = base64.b64decode(body.imageBase64, validate=True)
            if len(raw) > 5_000_000:
                raise ValueError('画面超过 5 MB')
            with Image.open(io.BytesIO(raw)) as im:
                if im.format not in {'JPEG', 'PNG'} or im.size != (body.width, body.height) or im.width * im.height > 16_000_000:
                    raise ValueError('图片格式或尺寸不符合回执')
                mime = 'image/jpeg' if im.format == 'JPEG' else 'image/png'
                im.verify()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
            raise ValueError('无法解码直播取样图片') from error
        frame = FrameRef(frame_id='live-' + uuid.uuid4().hex, device_id=s['deviceId'], channel_id='main',
                         captured_at=None, received_at=time.time(), source_type='official_live_' + s['platform'],
                         freshness='sampled_after_request', view_revision=s['id']+':'+str(s.get('viewVersion',0)),
                         sampled_at=body.sampledAt, request_id=body.requestId, session_id=s['id'])
        self.frames[frame.frame_id] = (frame, raw, mime)
        media = self.store.save_media(asdict(frame), raw, mime)
        s.update(sequence=max(s['sequence'], body.sequence), lastFrameUrl=media['imageUrl'], lastSampledAt=body.sampledAt)
        p['future'].set_result(frame)
        if getattr(self.store,'ops',None):
            self.store.ops.emit('capture.frame_accepted',trace=p.get('trace'),status='accepted',
                data=dict(deviceId=s['deviceId'],requestId=body.requestId,executor=s['platform'],
                    receivedAt=frame.received_at,sampledAt=body.sampledAt,capturedAt=None,
                    timestampMeaning='client_live_sample',frameId=frame.frame_id))
        return dict(status='accepted', frameId=frame.frame_id, imageUrl=media['imageUrl'],
                    capturedAt=None, timestampMeaning='client_live_sample', receivedAt=frame.received_at)

    async def manifests(self):
        self.expire()
        result = []
        for d in self.records():
            s = self.current(d['id'])
            ready = self.ready(s)
            result.append(DeviceManifest(d['id'], d['model'], d['name'], 'camera',
                'online' if ready else 'unknown', 'official-relay/' + d['platform'],
                (Channel('main', '当前 SDK 视频画面'),),
                dict(liveStream=CapabilityState.SUPPORTED if ready else CapabilityState.UNKNOWN,
                     liveSnapshot=CapabilityState.SUPPORTED if ready else CapabilityState.UNKNOWN,
                     ptz=CapabilityState.UNSUPPORTED if d['model'] == 'T8214' else CapabilityState.UNKNOWN),
                '前台直播取样；设备拍摄时间未知，不代表持续守护。' if ready else '设备已登记，等待授权客户端打开直播并提供新画面。',
                last_frame_url=s.get('lastFrameUrl') if s else None, last_captured_at=None))
        return result

    async def snapshot(self, device_id, kind, context=None):
        if kind != SnapshotKind.LIVE or not context:
            raise ValueError('实时取样需要服务端请求上下文')
        s = self.current(device_id)
        if not self.ready(s):
            raise ValueError('没有活跃的新画面输入，请在 iOS 或 Web 前台打开这台设备的直播')
        future = asyncio.get_running_loop().create_future()
        self.pending[context.request_id] = dict(sessionId=s['id'], deviceId=device_id,
            afterSequence=s['sequence'], deadline=context.deadline, future=future,trace=dict(CTX.get()))
        try:
            async with asyncio.timeout(max(0, context.deadline - time.time())):
                frame = await future
            return SnapshotReceipt(context.request_id, 'completed', kind, frame,
                                   '已取得本次请求后的直播取样；时间为客户端取样时间，设备拍摄时间未知。')
        finally:
            self.pending.pop(context.request_id, None)

    async def frame_bytes(self, device_id, frame_id):
        value = self.frames.get(frame_id)
        if not value or value[0].device_id != device_id:
            raise KeyError(frame_id)
        return value[1:]

    async def state(self):
        return dict(cameras=[dict(id=d['id'], transport_online=self.ready(self.current(d['id'])), observation=None)
                             for d in self.records()])

    async def shutdown(self):
        for s in self.sessions.values():
            self.stop(s)
        self.sessions.clear()
