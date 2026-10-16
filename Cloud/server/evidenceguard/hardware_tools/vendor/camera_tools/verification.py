"""Evidence classification. Official-demo baselines never authorize our executors."""
import json
import math
from pathlib import Path

from .catalog import ToolError

BASELINE_FILE = Path(__file__).resolve().parents[2] / "contracts/camera-tools/official-demo-baseline.json"


def variant(tool, arguments):
    if tool == "camera_ptz_step":
        return arguments.get("motionMode", "step")
    if tool == "device_settings_set":
        return arguments.get("field", "unspecified_field")
    if tool == "camera_record_clip":
        return "client_local:" + arguments.get("audioPolicy", "unspecified_audio")
    return "default"


def scope(device):
    return {"component": "evidenceguard_adapter", "platform": device["executorPlatform"],
            "deviceId": device["id"], "model": device["model"], "sdkVersion": device.get("sdkVersion", "unknown"),
            "sdkArtifactHash": device["sdkArtifactHash"], "firmwareVersion": device["firmwareVersion"],
            "capabilityRevision": device["capabilityRevision"]}


def reference_baselines(device):
    if not BASELINE_FILE.is_file():
        return []
    baseline = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
    s = baseline["scope"]
    if (device["executorPlatform"] != s["platform"] or device.get("sdkVersion") != s["sdkVersion"]
            or device["sdkArtifactHash"].lower() != s["sdkArtifactHash"].lower()):
        return []
    # Model comparison only. No claim that the registered unit, firmware or adapter was tested.
    return [{"scope": s, "notProductionAuthorization": True, "sameDeviceInstanceVerified": False,
             "sourceHashes": baseline["sourceHashes"],
             "cases": [c for c in baseline["cases"] if device["model"] in c["models"]]}]


def check_frame(frame, device_id, now_ms, max_age_ms=2000):
    """Clock is executor-local UTC, never a camera timestamp. Skew fails closed.

    A timed screenshot or bitrate is not a decoder progress signal. Two progressing
    frames in the same session are required, even when the room itself is static.
    """
    def fail(message):
        raise ToolError("STALE_FRAME", message)

    if not isinstance(frame, dict):
        fail("No decoded-frame provenance")
    if (frame.get("sourceKind") != "decoded_live_frame" or frame.get("deviceId") != device_id
            or frame.get("playState") != "playing" or not isinstance(frame.get("sessionId"), str)
            or not 0 < len(frame["sessionId"]) <= 128):
        fail("Frame source, session, device or play state is unconfirmed")
    sequence, previous = frame.get("sequence"), frame.get("previousSequence")
    if type(sequence) is not int or type(previous) is not int or not 0 <= previous < sequence:
        fail("Decoder frame sequence did not advance")
    if frame.get("progressSource") not in ("decoder_callback", "video_frame_timestamp"):
        fail("Frame progress must come from decoding, not timers or bandwidth")
    dims = frame.get("dimensions")
    if not isinstance(dims, list) or len(dims) != 2 or any(type(v) is not int or not 0 < v <= 16384 for v in dims):
        fail("Frame resolution is not ready")
    last, captured = frame.get("lastFrameAt"), frame.get("capturedAt")
    if any(type(t) not in (int, float) or not math.isfinite(t) for t in (last, captured)):
        fail("Missing finite frame timestamps")
    if not 0 <= captured - last <= max_age_ms or not 0 <= now_ms - last <= max_age_ms:
        fail("Decoded frame expired or clocks are inconsistent")
    return frame
