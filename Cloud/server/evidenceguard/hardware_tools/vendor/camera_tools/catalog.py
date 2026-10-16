"""Closed tool/field registry. Model input is never an SDK method or TD identifier."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MATRIX = json.loads((ROOT / "contracts/camera-tools/capabilities.json").read_text(encoding="utf-8"))


def string(*values):
    return {"type": "string", **({"enum": list(values)} if values else {"minLength": 1, "maxLength": 256})}


def integer(low, high):
    return {"type": "integer", "minimum": low, "maximum": high}


def array(item, maximum=32):
    return {"type": "array", "items": item, "maxItems": maximum}


BOOL = {"type": "boolean"}
DEVICE = {"deviceId": string()}
TOOLS = {}


def tool(name, title, caps, properties, required=(), control=False, device=True):
    props = {**(DEVICE if device else {}), **properties}
    TOOLS[name] = {"name": name, "description": title, "capabilities": caps.split("/"),
                   "control": control,
                   "inputSchema": {"type": "object", "additionalProperties": False,
                                   "properties": props,
                                   "required": (["deviceId"] if device else []) + list(required)}}


tool("devices_list", "列出当前授权范围的设备，不推断实时在线状态", "C01", {}, device=False)
tool("device_inspect", "读取登记能力、来源和未验证项", "C02", {})
tool("camera_observe", "获取新直播帧，不移动设备", "C07", {"freshness": integer(1, 60)})
tool("camera_events_query", "查询带来源的历史事件", "C10", {"from": integer(0, 9999999999), "to": integer(0, 9999999999), "cursor": string(), "types": array(string())})
tool("camera_ptz_step", "有限方向单步；移动后旧观察失效", "C16", {"direction": string("LEFT", "RIGHT", "UP", "DOWN"), "referenceObservationId": string(), "expectedViewRevision": integer(0, 2147483647)}, ("direction", "referenceObservationId", "expectedViewRevision"), True)
tool("camera_goto_preset", "跳转本设备真实预置位目录中的位置", "C17", {"presetRef": string(), "referenceObservationId": string()}, ("presetRef", "referenceObservationId"), True)
tool("camera_set_night_vision", "使用同一设置路线的选项；首版仅持久设置", "C20", {"optionRef": string(), "scope": string("persistent")}, ("optionRef", "scope"), True)
tool("doorbell_light_set", "T8214 灯光兼容入口", "C23", {"channelRef": string(), "enabled": BOOL}, ("channelRef", "enabled"), True)
tool("doorbell_reply_play", "播放已准备的设备回复，不接受任意 TTS 文本", "C25", {"replyRef": string()}, ("replyRef",), True)
tool("camera_record_clip", "有限客户端录制；严格检查采集音轨策略", "C13", {"duration": integer(1, 30), "audioPolicy": string("required", "forbidden", "allowIfPresent")}, ("duration", "audioPolicy"), True)
tool("operation_get", "读取本任务操作；ACK 不代表物理结果", "C42", {"operationId": string()}, ("operationId",), device=False)
tool("camera_stop", "停止指定操作；逐项返回停止结果", "C42", {"operationId": string()}, ("operationId",), device=False)
tool("device_state_get", "读取真实状态，未获取字段为 UNKNOWN", "C02", {"fields": array(string("privacy", "battery", "network", "storage", "version"))})
tool("device_settings_get", "读取注册设置字段与可用选项", "C21", {"fields": array(string())})
tool("device_settings_set", "仅设置白名单字段；需要版本、选项和用户确认", "C21", {"field": string(), "value": {}, "expectedSettingsRevision": integer(0, 2147483647)}, ("field", "value", "expectedSettingsRevision"), True)
tool("camera_events_subscribe", "建立有限期事件订阅", "C11", {"types": array(string()), "duration": integer(1, 300)}, ("duration",))
tool("camera_events_unsubscribe", "解除指定订阅", "C11", {"subscriptionId": string()}, ("subscriptionId",), device=False)
tool("camera_event_get", "读取当前任务有权访问的事件详情", "C10", {"eventRef": string()}, ("eventRef",), device=False)
tool("camera_evidence_get", "读取授权媒体元数据，不接收任意 URL", "C12", {"mediaRef": string()}, ("mediaRef",), device=False)
tool("camera_evidence_download", "下载指定证据；目标限受控存储", "C12", {"mediaRef": string(), "destination": string("executorLocal")}, ("mediaRef", "destination"), device=False)
tool("camera_presets_list", "读取本设备真实预置位目录", "C17", {})
tool("doorbell_replies_list", "读取已准备的门铃回复目录", "C25", {})
tool("camera_talk_start", "从人授权的执行端麦克风开启有限期普通对讲", "C14", {"microphoneSessionRef": string(), "duration": integer(1, 30)}, ("microphoneSessionRef", "duration"), True)
tool("camera_talk_stop", "停止普通对讲操作并释放资源", "C14", {"operationId": string()}, ("operationId",), device=False)
tool("camera_light_set", "设置已登记的灯光通道", "C23", {"channelRef": string(), "enabled": BOOL}, ("channelRef", "enabled"), True)
tool("camera_dual_mode_set", "切换已验证的双摄布局，更新视图版本", "C27", {"modeRef": string(), "expectedViewRevision": integer(0, 2147483647)}, ("modeRef", "expectedViewRevision"), True)
tool("camera_ptz_mode_set", "条件扩展：仅诊断或已验证的跟踪/巡航", "C19", {"modeRef": string()}, ("modeRef",), True)
tool("camera_panorama_generate", "条件扩展：按已验证选项生成全景", "C34", {"optionRef": string()}, ("optionRef",), True)
tool("operation_cancel", "取消未发出的操作，已发出的操作请求停止", "C42", {"operationId": string()}, ("operationId",), device=False)

# Each field has its own capability. No privacy-off, alarm, deletion, calibration,
# formatting, OTA, clock/name mutation, unbinding or arbitrary property escape.
FIELDS = {
    "ptzSpeed": ("C18", integer(1, 5)),
    "videoQuality": ("C21", string()),
    "microphoneEnabled": ("C22", BOOL),
    "speakerVolume": ("C22", integer(0, 100)),
    "audioRecordEnabled": ("C22", BOOL),
    "statusLED": ("C24", BOOL),
    "motionEnabled": ("C28", BOOL),
    "motionSensitivity": ("C28", integer(0, 100)),
    "detectionTypes": ("C29", array(string())),
    "soundEnabled": ("C30", BOOL),
    "notificationEnabled": ("C32", BOOL),
    "packageGuardEnabled": ("C33", BOOL),
    "powerMode": ("C35", string()),
}


class ToolError(Exception):
    def __init__(self, code, message, status=400):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


def check(schema, value, path="arguments"):
    kind = schema.get("type")
    valid = {"object": lambda: isinstance(value, dict), "array": lambda: isinstance(value, list),
             "string": lambda: isinstance(value, str), "integer": lambda: type(value) is int,
             "boolean": lambda: type(value) is bool}
    if kind and not valid[kind]():
        raise ToolError("UNSUPPORTED_PARAMETER", f"{path}: expected {kind}")
    if "enum" in schema and value not in schema["enum"]:
        raise ToolError("UNSUPPORTED_PARAMETER", f"{path}: option not registered")
    if kind == "object":
        if set(schema.get("required", [])) - value.keys():
            raise ToolError("UNSUPPORTED_PARAMETER", f"{path}: missing required field")
        if schema.get("additionalProperties") is False and value.keys() - schema["properties"].keys():
            raise ToolError("UNSUPPORTED_PARAMETER", f"{path}: unregistered field")
        for key, val in value.items():
            check(schema.get("properties", {}).get(key, {}), val, f"{path}.{key}")
    if kind == "integer" and not schema.get("minimum", value) <= value <= schema.get("maximum", value):
        raise ToolError("UNSUPPORTED_PARAMETER", f"{path}: out of range")
    if kind == "string" and not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 256):
        raise ToolError("UNSUPPORTED_PARAMETER", f"{path}: invalid length")
    if kind == "array":
        if len(value) > schema.get("maxItems", 32):
            raise ToolError("UNSUPPORTED_PARAMETER", f"{path}: too many items")
        for item in value:
            check(schema["items"], item, path)


def support(capability, platform, model):
    return next(row for row in MATRIX["capabilities"] if row["id"] == capability)["platforms"][platform][model]
