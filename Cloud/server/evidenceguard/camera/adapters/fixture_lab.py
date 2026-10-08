from __future__ import annotations

import asyncio
import time
import uuid

import httpx

from ..contracts import CapabilityState, Channel, DeviceManifest, FrameRef, SnapshotKind, SnapshotReceipt, CameraCommandContext


class FixtureLabAdapter:
    """Adapter for the local RTSP fixture; never presented as a physical camera SDK."""

    def __init__(self, base_url: str = "http://127.0.0.1:8787") -> None:
        self.base_url = base_url.rstrip("/")

    async def state(self) -> dict:
        async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
            response = await client.get(f"{self.base_url}/api/state")
            response.raise_for_status()
            return response.json()

    async def manifests(self) -> list[DeviceManifest]:
        try:
            state = await self.state()
            raw = {camera["id"]: camera for camera in state.get("cameras", [])}
        except (httpx.HTTPError, ValueError):
            raw = {}
        specs = (("cam-a", "T8171", "屋檐摄像头", "primary"), ("cam-b", "T8214", "门铃摄像头", "supplementary"))
        values = []
        for device_id, model, name, role in specs:
            camera = raw.get(device_id, {})
            values.append(DeviceManifest(
                id=device_id, model=model, name=name, role=role,
                connection="online" if camera.get("transport_online") else ("offline" if camera else "unknown"),
                adapter="fixture-lab/v1",
                channels=(Channel("main", "主码流"),),
                capabilities={
                    "storedSnapshot": CapabilityState.UNSUPPORTED,
                    "liveSnapshot": CapabilityState.SUPPORTED,
                    "liveStream": CapabilityState.SUPPORTED,
                    "eventPush": CapabilityState.SUPPORTED,
                    "ptz": CapabilityState.UNSUPPORTED,
                },
                evidence="本地合成画面经 RTSP 实际传输；能力来自适配器握手。",
                last_frame_url=(f"/api/camera/frames/{device_id}/{camera['observation']['frame_id']}.jpg" if camera.get("observation") else None),
                last_captured_at=(camera.get("observation") or {}).get("captured_at"),
            ))
        return values

    async def snapshot(self, device_id: str, kind: SnapshotKind, context: CameraCommandContext | None = None) -> SnapshotReceipt:
        if kind is SnapshotKind.STORED:
            return SnapshotReceipt(str(uuid.uuid4()), "unsupported", kind, None, "fixture 不提供历史缩略图")
        async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
            response = await client.post(self.base_url + '/api/cameras/snapshot', json={'camera_id': device_id})
            response.raise_for_status()
            command = response.json()
            deadline = time.monotonic() + 5.8
            while command['status'] == 'accepted' and time.monotonic() < deadline:
                await asyncio.sleep(.2)
                response = await client.get(self.base_url + '/api/cameras/requests/' + command['id'])
                response.raise_for_status(); command = response.json()
        item = command.get('frame')
        if command['status'] != 'completed' or not item:
            return SnapshotReceipt(command['id'], 'failed', kind, None, '请求未获得新画面：' + command['status'])
        if item['captured_at'] < command['requested_at'] or time.time()-item['captured_at'] > 6:
            return SnapshotReceipt(command['id'], 'failed', kind, None, '返回的是旧画面，不作为本次观察')
        frame = FrameRef(
            frame_id=item['frame_id'], device_id=device_id, channel_id=item.get('channel_id', 'main'),
            captured_at=item['captured_at'], received_at=item['received_at'], source_type='fixture',
            freshness='live', view_revision=f"fixture-{item['revision']}", clock_offset_ms=0,
            uncertainty_ms=40, calibration_ref=f'fixture:{device_id}:v1',
        )
        return SnapshotReceipt(command['id'], 'completed', kind, frame, '已取得请求之后采集的新画面')

    async def frame_bytes(self, device_id: str, frame_id: str) -> tuple[bytes, str]:
        if not frame_id.startswith(f"{device_id}-") or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-" for char in frame_id):
            raise ValueError("invalid frame id")
        async with httpx.AsyncClient(timeout=4, trust_env=False) as client:
            response = await client.get(f"{self.base_url}/api/frames/{frame_id}.jpg")
            response.raise_for_status()
            return response.content, response.headers.get("content-type", "image/jpeg")
