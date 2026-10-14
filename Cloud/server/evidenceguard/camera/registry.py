from __future__ import annotations

from .contracts import CameraAdapter, DeviceManifest, SnapshotKind, SnapshotReceipt, CameraCommandContext

class EmptyCameraAdapter:
    async def manifests(self): return []
    async def state(self): return {'cameras': []}
    async def snapshot(self, *args): raise KeyError('camera')
    async def frame_bytes(self, *args): raise KeyError('frame')

class RoutedCameraAdapter:
    """Bind cam-a/cam-b to separate official SDK adapters without changing business code."""
    def __init__(self, adapters: dict[str, CameraAdapter]):
        self.adapters = adapters

    async def manifests(self):
        result=[]
        for device_id, adapter in self.adapters.items():
            manifests=await adapter.manifests()
            if len(manifests)!=1 or manifests[0].id!=device_id:
                raise ValueError('摄像头适配器路由身份不匹配')
            result.extend(manifests)
        return result

    async def snapshot(self, device_id, kind, context=None):
        return await self.adapters[device_id].snapshot(device_id,kind,context)

    async def frame_bytes(self, device_id, frame_id):
        return await self.adapters[device_id].frame_bytes(device_id,frame_id)

    async def state(self):
        result=[]
        for device_id, adapter in self.adapters.items():
            try:
                state=await adapter.state()
                result.extend(c for c in state.get('cameras',[]) if c['id']==device_id)
            except (RuntimeError, OSError):
                result.append(dict(id=device_id,transport_online=False,observation=None))
        return {'cameras':result}


class CameraRegistry:
    def __init__(self, active: CameraAdapter) -> None:
        self.active = active
        self.replay = None
        self.live = None

    async def manifests(self) -> list[DeviceManifest]:
        return await self.active.manifests() + (await self.live.manifests() if self.live else [])

    async def snapshot(self, device_id: str, kind: SnapshotKind, context: CameraCommandContext | None = None) -> SnapshotReceipt:
        manifests = await self.manifests()
        if not any(item.id == device_id for item in manifests):
            raise KeyError(device_id)
        adapter = self.live if self.live and any(d['id'] == device_id for d in self.live.records()) else self.active
        return await adapter.snapshot(device_id, kind, context)

    async def state(self) -> dict:
        value = await self.active.state()
        if self.live:
            value = {'cameras': value.get('cameras', []) + (await self.live.state())['cameras']}
        return value

    async def frame_bytes(self, device_id: str, frame_id: str) -> tuple[bytes, str]:
        adapter = self.live if self.live and any(d['id'] == device_id for d in self.live.records()) else self.active
        return await adapter.frame_bytes(device_id, frame_id)

    async def replay_window(self, device_id, recording_id, start, end, context, region):
        if self.replay is None: raise ValueError('回放适配器未接入')
        return await self.replay.window(device_id,recording_id,start,end,context,region)

    async def replay_sample(self,device_id,recording_id,at,context,region):
        if self.replay is None:raise ValueError('回放适配器未接入')
        return await self.replay.sample(device_id,recording_id,at,context,region)
