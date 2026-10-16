"""Capability-checked capture with durable receipts shared by Agent and Worker."""
from __future__ import annotations
from ..ops import traced
import asyncio, time, uuid
from dataclasses import asdict
from contextlib import asynccontextmanager, AsyncExitStack
from .contracts import CapabilityState, SnapshotKind, CameraCommandContext
from ..harness.scheduler import TaskEnvelope

class CameraService:
    def __init__(self, store, cameras, scheduler):
        self.store, self.cameras, self.scheduler = store, cameras, scheduler
        self.device_locks = {}
        self.transition_lock = asyncio.Lock()

    def gate(self, device_id):
        return self.device_locks.setdefault(device_id, asyncio.Lock())

    @asynccontextmanager
    async def transition(self):
        # Single-device operations and multi-device activation share the same gates.
        # Drain current commands before changing ownership; queued commands recheck epoch.
        async with self.transition_lock:
            devices = {d for s in self.store.skills() for d in s['devices']} | set(self.device_locks)
            async with AsyncExitStack() as stack:
                for d in sorted(devices): await stack.enter_async_context(self.gate(d))
                yield

    @traced('camera.capture')
    async def capture(self, device_id, skill_id=None, purpose='用户请求观察'):
        request_id = 'capture-' + uuid.uuid4().hex
        epoch = self.store.capture_context(device_id, skill_id)
        async def perform():
            async with self.gate(device_id):
                return await locked_capture()
        async def locked_capture():
            receipt = dict(id=request_id, cameraId=device_id, skillId=skill_id, status='failed',
                           reason='摄像头暂不可用', requestedAt=time.time(), purpose=purpose)
            self.store.event(skill_id or request_id, 'camera_requested', receipt)
            live = getattr(self.cameras, 'live', None)
            try:
                async with asyncio.timeout(28):
                    if getattr(self,'hardware_busy',lambda _:False)(device_id):
                        raise ValueError('设备控制尚未结束或结果未知，暂不使用当前视角判断')
                    if self.store.capture_context(device_id, skill_id) != epoch:
                        raise ValueError('任务已切换，本次旧请求不再执行')
                    owner=self.store.owner(device_id)
                    if owner and owner.get('replay'): raise ValueError('此摄像头正在执行录像回放测试；请查看任务回放证据，不把模拟设备新图混入回放')
                    manifest = next((m for m in await self.cameras.manifests() if m.id == device_id), None)
                    if not manifest: raise ValueError('摄像头不存在')
                    # Ask the foreground single-player client to select this
                    # device and wait for its decoded frame/cloud heartbeat.
                    # A fresh challenged snapshot is still required afterward.
                    if live and any(d['id'] == device_id for d in live.records()):
                        live.demands[request_id] = dict(deviceId=device_id, deadline=time.time()+28)
                    if manifest.connection != 'online' and live and any(live.current(d['id']) for d in live.records()):
                        until = time.monotonic() + 20
                        while manifest.connection != 'online' and time.monotonic() < until:
                            await asyncio.sleep(.15)
                            manifest = next((m for m in await self.cameras.manifests() if m.id == device_id), manifest)
                    if manifest.connection != 'online':
                        if manifest.adapter.startswith('official'):
                            raise ValueError('摄像头已登记，当前实时画面会话未就绪。请在 App 前台连接画面后重试；这不表示设备未添加或设备离线。')
                        raise ValueError('摄像头当前连接不可用，不能取得新画面')
                    if manifest.capabilities.get('liveSnapshot') != CapabilityState.SUPPORTED:
                        receipt.update(status='unsupported', reason='该设备的新鲜截图能力尚未就绪')
                    else:
                        if self.store.capture_context(device_id, skill_id) != epoch:
                            raise ValueError('任务已切换，本次旧请求不再执行')
                        context = CameraCommandContext(request_id, skill_id or request_id, epoch or request_id, time.time()+8)
                        result = await self.cameras.snapshot(device_id, SnapshotKind.LIVE, context)
                        if self.store.capture_context(device_id, skill_id) != epoch:
                            raise ValueError('任务已切换，丢弃旧任务的画面回执')
                        receipt.update(status=result.status, reason=result.reason, deviceRequestId=result.request_id)
                        if result.status == 'completed' and result.frame:
                            f = result.frame
                            if f.device_id != device_id:
                                raise ValueError('返回画面身份或采集时间无效')
                            if f.captured_at is None:
                                if (f.freshness != 'sampled_after_request' or f.request_id != request_id
                                    or not f.session_id or f.sampled_at is None
                                    or not receipt['requestedAt'] <= f.received_at <= time.time()
                                    or time.time() - f.received_at > 6):
                                    raise ValueError('返回画面未对应本轮实时取样请求')
                            elif f.captured_at < receipt['requestedAt'] - (f.uncertainty_ms or 0)/1000 or not -.5 <= time.time()-f.captured_at <= 6:
                                raise ValueError('返回画面身份或采集时间无效')
                            raw, mime = await self.cameras.frame_bytes(device_id, f.frame_id)
                            media = self.store.save_media(asdict(f), raw, mime)
                            receipt.update(status='completed', frameId=f.frame_id, capturedAt=f.captured_at,
                                           imageUrl=media['imageUrl'], mediaId=media['id'], sourceType=f.source_type,
                                           viewRevision=f.view_revision, sampledAt=f.sampled_at, receivedAt=f.received_at,
                                           timestampMeaning='device_capture' if f.captured_at is not None else 'client_live_sample')
            except asyncio.CancelledError:
                receipt.update(status='cancelled', reason='已取消本次画面请求')
                self.store.event(skill_id or request_id, 'camera_cancelled', receipt)
                raise
            except (ValueError, KeyError) as error:
                receipt.update(status='failed', reason=str(error))
            except Exception:
                receipt.update(status='failed', reason='获取新画面超时或失败，没有更新观察结论')
            finally:
                if live: live.demands.pop(request_id, None)
            self.store.event(skill_id or request_id, 'camera_completed' if receipt['status']=='completed' else 'camera_failed', receipt)
            return receipt
        return await self.scheduler.submit(TaskEnvelope(request_id, 'camera', skill_id), perform)

    async def replay_window(self, skill, start, end):
        device=skill['target']['cameraId']; epoch=skill['executionEpoch']
        async with self.gate(device):
            if self.store.capture_context(device,skill['id'])!=epoch: raise ValueError('任务已切换')
            context=CameraCommandContext('window-'+uuid.uuid4().hex,skill['id'],epoch,time.time()+120)
            result=await self.cameras.replay_window(device,skill['replay']['recordingId'],start,end,context,skill['regions'][device])
            if self.store.capture_context(device,skill['id'])!=epoch: raise ValueError('任务已切换，丢弃旧窗口')
            return result

    async def replay_sample(self,skill,at):
        device=skill['target']['cameraId'];epoch=skill['executionEpoch']
        async with self.gate(device):
            if self.store.capture_context(device,skill['id'])!=epoch:raise ValueError('任务已切换')
            context=CameraCommandContext('sample-'+uuid.uuid4().hex,skill['id'],epoch,time.time()+120)
            result=await self.cameras.replay_sample(device,skill['replay']['recordingId'],at,context,skill['regions'][device])
            if self.store.capture_context(device,skill['id'])!=epoch:raise ValueError('丢弃旧任务样本')
            return result
