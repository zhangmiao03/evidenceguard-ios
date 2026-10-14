"""Read the native SDK relay cache without inventing a live camera session."""
import json
import uuid
from ..contracts import CapabilityState, DeviceManifest, SnapshotReceipt


class SDKEventsAdapter:
    def __init__(self, store): self.store=store

    async def manifests(self):
        with self.store.lock:
            rows=self.store.db.execute('SELECT payload FROM sdk_devices ORDER BY id').fetchall()
        result=[]
        for row in rows:
            device=json.loads(row[0])
            with self.store.lock:
                latest=self.store.db.execute('SELECT payload FROM sdk_events WHERE camera=? ORDER BY received DESC LIMIT 1',(device['id'],)).fetchone()
            event=json.loads(latest[0]) if latest else None
            result.append(DeviceManifest(
                id=device['id'],model=device['model'],name=device['name'],role='event_source',
                connection='event_only',adapter='official-sdk/event-relay',channels=(),
                capabilities={key:CapabilityState.UNSUPPORTED for key in ('liveSnapshot','liveStream','eventPush','ptz')}
                             | {'storedSnapshot':CapabilityState.SUPPORTED if event and event['imageUrl'] else CapabilityState.UNKNOWN},
                evidence='由手机官方 SDK 同步的设备和事件；当前仅支持读取已收到的事件图片。',
                last_frame_url=event['imageUrl'] if event else None,
                # Event time does not prove when its thumbnail was captured.
                last_captured_at=None))
        return result

    async def state(self): return {'cameras':[]}

    async def snapshot(self, device_id, kind, context=None):
        return SnapshotReceipt('sdk-cache-'+uuid.uuid4().hex,'unsupported',kind,None,'目前只有已同步的事件图片，尚未接通实时截图。')

    async def frame_bytes(self, device_id, frame_id):
        raise ValueError('事件图片请通过已保存的证据读取')
