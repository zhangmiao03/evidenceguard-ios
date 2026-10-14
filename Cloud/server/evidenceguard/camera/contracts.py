from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Protocol


class CapabilityState(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class SnapshotKind(StrEnum):
    STORED = "stored"
    LIVE = "live"


@dataclass(frozen=True)
class Channel:
    id: str
    label: str
    kind: str = "video"


@dataclass(frozen=True)
class DeviceManifest:
    id: str
    model: str
    name: str
    role: str
    connection: str
    adapter: str
    channels: tuple[Channel, ...]
    capabilities: dict[str, CapabilityState]
    evidence: str
    last_frame_url: str | None = None
    last_captured_at: float | None = None

    def api_dict(self) -> dict:
        value = asdict(self)
        value["lastFrameUrl"] = value.pop("last_frame_url")
        value["lastCapturedAt"] = value.pop("last_captured_at")
        return value


@dataclass(frozen=True)
class FrameRef:
    frame_id: str
    device_id: str
    channel_id: str
    captured_at: float | None
    received_at: float
    source_type: str
    freshness: str
    view_revision: str
    clock_offset_ms: int | None = None
    uncertainty_ms: int | None = None
    calibration_ref: str | None = None
    sampled_at: float | None = None
    request_id: str | None = None
    session_id: str | None = None


@dataclass(frozen=True)
class SnapshotReceipt:
    request_id: str
    status: str
    kind: SnapshotKind
    frame: FrameRef | None
    reason: str

@dataclass(frozen=True)
class CameraCommandContext:
    request_id: str
    owner_id: str
    execution_epoch: str
    deadline: float

@dataclass(frozen=True)
class StoredRecordingRef:
    recording_id: str
    device_id: str
    channel_id: str
    recorded_start: float | None
    recorded_end: float | None
    clock_uncertainty_ms: int | None
    source_reference: str


@dataclass(frozen=True)
class SessionVideoWindow:
    """Reserved SDK ingestion receipt; file contains only already received frames.

    captured_* use the device capture timeline, received_at the server clock.
    Unknown device clock remains None; callers must never substitute processing time.
    """
    device_id: str
    channel_id: str
    session_id: str
    execution_epoch: str
    captured_start: float | None
    captured_end: float | None
    received_at: float
    clock_uncertainty_ms: int | None
    local_path: str


class OfficialSDKBridge(Protocol):
    """Organizer integration boundary; credentials stay with the SDK session owner.

    App SDK credentials live in the native client's Keychain; any future cloud
    relay must transport scoped commands/receipts, never expose credentials as
    Agent tools. The first foreground iOS/Web relay is implemented separately
    by LiveDevices; this protocol remains the direct hardware/control port.

    snapshot must finish (or acknowledge cancellation) before returning/raising;
    detached hardware commands must not outlive their ownership epoch.
    state/frame_bytes only read the ingestion cache, never start device commands.
    """
    async def manifest(self, device_id: str, model: str) -> DeviceManifest: ...
    async def snapshot(self, device_id: str, kind: SnapshotKind, context: CameraCommandContext) -> SnapshotReceipt: ...
    async def state(self, device_id: str) -> dict: ...
    async def frame_bytes(self, device_id: str, frame_id: str) -> tuple[bytes, str]: ...
    # Reserved for long-lived SDK sessions. Not exposed as Agent tools until verified.
    async def start_session(self, device_id: str, context: CameraCommandContext) -> str: ...
    async def stop_session(self, device_id: str, session_id: str, context: CameraCommandContext) -> None: ...
    # Reserved rolling-window port. Not called until organizer capability validation.
    # Implementations must enforce max_seconds, epoch/cancellation, bounded local
    # files, and return only frames ingested by the supplied receive-time cutoff.
    async def read_session_window(self, device_id: str, session_id: str, received_before: float, max_seconds: float, context: CameraCommandContext) -> SessionVideoWindow: ...
    # Reserved SDK import boundary, not a history analysis tool. Device I/O must
    # be scheduled via CameraService; already-imported video search never calls this.
    async def list_recordings(self, device_id: str, start: float, end: float, context: CameraCommandContext) -> list[StoredRecordingRef]: ...
    async def export_recording(self, recording: StoredRecordingRef, destination: str, context: CameraCommandContext) -> None: ...


class CameraAdapter(Protocol):
    async def manifests(self) -> list[DeviceManifest]: ...
    async def snapshot(self, device_id: str, kind: SnapshotKind, context: CameraCommandContext | None = None) -> SnapshotReceipt: ...
    async def state(self) -> dict: ...
    async def frame_bytes(self, device_id: str, frame_id: str) -> tuple[bytes, str]: ...
