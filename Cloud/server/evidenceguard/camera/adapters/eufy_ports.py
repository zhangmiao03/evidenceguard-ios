from __future__ import annotations

from ..contracts import CapabilityState, Channel, DeviceManifest, SnapshotKind, SnapshotReceipt, CameraCommandContext, OfficialSDKBridge


class _PendingEufyAdapter:
    """Typed port for the organizer-provided SDK. It intentionally claims no unverified capability."""

    device_id = ""
    model = ""
    name = ""
    role = ""

    def __init__(self, bridge: OfficialSDKBridge | None = None):
        self.bridge = bridge

    def check_device(self, device_id):
        if device_id != self.device_id: raise ValueError('SDK 设备身份不匹配')

    async def manifests(self) -> list[DeviceManifest]:
        if self.bridge:
            manifest = await self.bridge.manifest(self.device_id, self.model)
            if manifest.id != self.device_id or manifest.model != self.model:
                raise ValueError('SDK 握手返回了错误的设备身份')
            return [manifest]
        return [DeviceManifest(
            id=self.device_id, model=self.model, name=self.name, role=self.role, connection="unknown",
            adapter=f"eufy-official/{self.model}/pending",
            channels=(Channel("main", "待 SDK 枚举"),),
            capabilities={key: CapabilityState.UNKNOWN for key in ("storedSnapshot", "liveSnapshot", "liveStream", "eventPush", "ptz")},
            evidence="官方 SDK 已收到，设备接入尚未验证；能力必须在握手后更新。",
        )]

    async def state(self) -> dict:
        if self.bridge: return await self.bridge.state(self.device_id)
        raise RuntimeError(f"{self.model} official SDK is not configured")

    async def snapshot(self, device_id: str, kind: SnapshotKind, context: CameraCommandContext | None = None) -> SnapshotReceipt:
        self.check_device(device_id)
        if self.bridge:
            if not context: raise ValueError('SDK 调用必须带有摄像头占用凭据')
            return await self.bridge.snapshot(device_id, kind, context)
        return SnapshotReceipt(f"pending-{self.model}", "failed", kind, None, "正式 SDK 尚未配置")

    async def frame_bytes(self, device_id: str, frame_id: str) -> tuple[bytes, str]:
        self.check_device(device_id)
        if self.bridge: return await self.bridge.frame_bytes(device_id, frame_id)
        raise RuntimeError("official SDK is not configured")


class EufyT8171Adapter(_PendingEufyAdapter):
    device_id = "cam-a"
    model = "T8171"
    name = "屋檐摄像头"
    role = "primary"


class EufyT8214Adapter(_PendingEufyAdapter):
    device_id = "cam-b"
    model = "T8214"
    name = "门铃摄像头"
    role = "supplementary"
