# 摄像头 SDK 接入合同

## 为什么先固定合同

2026-10-08 已收到 T8171、T8214 官方 App / Web SDK。最小业务合同继续保留，RTSP 夹具只用于模拟。App 增加原生 Kotlin 设备发现、事件列表和缩略图联调；Web 增加直播与按秒抽帧联调入口。官方 App SDK 的 AI 路径是事件触发后读取缩略图/录像，不提供持续视频帧供 AI 分析。2026-10-12 增加了原生事件元数据和事件图片到 Cloud 的只读导入协议；命令转发、持续后台采集及真机验收仍未接通，不能把这些入口视为完整的真机 Adapter。双端边界见 [Web / App 协作架构](../Docs/WEB-APP-ARCHITECTURE.md)。

## 设备能力清单

每个适配器必须在运行时返回：设备与通道身份、连接状态、适配器版本，以及下列三态能力：

- `supported`：SDK 握手或实际调用已证明支持。
- `unsupported`：SDK 明确拒绝或没有该能力。
- `unknown`：没有证据，不能猜测。

当前探测项为 `storedSnapshot / liveSnapshot / liveStream / eventPush / ptz`。业务逻辑按能力分支，不按 T8171/T8214 型号分支。

## FrameRef

每帧必须带：

```text
frameId, deviceId, channelId,
capturedAt, receivedAt,
sourceType, freshness,
viewRevision,
clockOffsetMs, uncertaintyMs, calibrationRef
```

`viewRevision` 用于隔离分辨率、裁剪或旋转发生变化后的坐标；时钟偏移与误差用于判断两机画面能否组成同一次观察。目标框与关注区域都用 0–1 归一化坐标保存。

## 截图语义

`SnapshotKind.STORED` 和 `SnapshotKind.LIVE` 是两个独立操作。历史缩略图不能冒充请求之后的新鲜画面；重新检查必须请求 `LIVE`，失败时结果保持 `unknown`。

## 两个正式端口

- `EufyT8171Adapter`：主观察设备 `cam-a`。
- `EufyT8214Adapter`：补证设备 `cam-b`。

它们当前均返回 `connection=unknown` 和全量 `capability=unknown`，这是刻意的真实性保护。SDK 到手后的实现顺序：发现设备 → 绑定设备/通道身份 → 读取 capability manifest → 验证 stored/live 差异 → 验证事件推送 → 验证流分辨率切换 → 验证双机时间偏移。

2026-10-09 仍无实机与赛事凭证。App 联调页展示 SDK 原始能力声明，不自动将它提升为 Cloud 的 `supported`；设备缩略图、缓存封面和事件图片只读结果均不能满足 `LIVE` 的新鲜度要求。

## v0.4：SDK Bridge 与摄像头占用

`camera/contracts.py` 的 `OfficialSDKBridge` 是可注入端口，两款 Adapter 均接受 `bridge=`：

```python
from evidenceguard.app import create_app
from evidenceguard.camera.registry import RoutedCameraAdapter
from evidenceguard.camera.adapters.eufy_ports import EufyT8171Adapter, EufyT8214Adapter

# bridge 需要把原生/浏览器会话接到云端端口；当前没有 Linux/Python 官方 SDK 实现。
app = create_app(camera_adapter=RoutedCameraAdapter({
    'cam-a': EufyT8171Adapter(bridge),
    'cam-b': EufyT8214Adapter(bridge),
}))
```

- `manifest(device_id, model)`：握手、能力、设备/通道身份；返回错误型号或 ID 会被拒绝。
- `snapshot(device_id, kind, context)`：收到 `request_id / owner_id / execution_epoch / deadline`，由 SDK wrapper 转换为真实请求并返回 SnapshotReceipt。没有占用上下文的正式端口调用会被拒绝。
- `state(device_id)`：**只读**已入站事件/观察缓存，统一返回 `{'cameras': [...]}`；不得借轮询启动流、转动或触发取图。
- `frame_bytes(device_id, frame_id)`：**只读**已入站且绑定 frame_id 的缓存，不得把“最新图”伪装成指定帧。
- `start_session / stop_session`：为长时间拉流或控制会话预留的 Protocol，目前不调用。启用真实流或 PTZ 前，需要补齐停止回执、故障恢复及设备能力验收，不能只打开 capability 开关。

所有主动设备命令必须经 CameraService；每台设备独占范围包含所有通道。主/补摄像头一起占用，切换先等待在途调用结束，再原子变更所有权。已排队的旧 epoch 请求不得发给 SDK，迟到回执不得写入新任务。

SDK snapshot 必须在返回或抛出取消异常前完成/确认取消设备命令；不允许 fire-and-forget 后立即释放锁。如果 SDK 无法确认停止，应隔离设备并报告 unknown，不能声称已安全切换。本版模拟截图没有持久控制会话，真实 SDK 的取消与隔离行为仍待实现验证。

历史分析不调用以上设备接口，只读服务端保存的媒体；首次从设备导入历史录像将是单独的导入流程，不属于“只读历史分析”。v0.5 已支持本地视频导入；SDK 获取录像尚未实现。

适配器替换只完成设备通路。当前启用校验和 Worker 仍是 fixture-marker/v1 测试执行器；正式 SDK 到手后还需接入通用视觉执行器及对应确认流程，不能直接把真机画面当作测试标记结果。

## 参考带来的具体约束

[eufy-sdk](https://github.com/mega-yfue/eufy-sdk) 展示了 capability-driven 设备、stored/live snapshot 分离、共享媒体拉流和 HomeBase 通道归属。项目是非官方 Apache-2.0 参考，本仓库没有复制其源代码，也不会把它当作主办方官方接口。

[NVIDIA PhysicalAI-SmartSpaces](https://huggingface.co/datasets/nvidia/PhysicalAI-SmartSpaces) 提供同步多视角、跨视角身份与相机标定的数据组织参考。它并非本项目的箱子数据集，因此只参考 schema，不把它当成模型效果证明。

## v0.5 历史录像接口预留

`StoredRecordingRef` 包含录像 ID、设备/通道 ID、可空的采集起止时间、时间不确定度与源引用。`OfficialSDKBridge.list_recordings(device_id, start, end, context)` 和 `export_recording(recording, destination, context)` 仅为预留合同，尚未调用，也未暴露给历史 Agent。

后续 SDK 导入器先通过 CameraService 获取必要的设备执行凭据，导出到受控本地文件，再交给 VideoService.stage/index。若厂商接口占用设备流或视角，必须服从该设备实时任务的所有权，不能因“历史录像”就绕过占用。视频入库后，search_recordings 只读本地文件及索引，可与守护并行。实际 SDK 签名和设备导出能力收到文档后再映射，不推断 T8171/T8214 已支持。

## v0.7：已接收视频窗口合同

新增 `SessionVideoWindow` 与预留 `OfficialSDKBridge.read_session_window(device_id, session_id, received_before, max_seconds, context)`。返回设备、通道、会话、执行代次、可空的采集起止时间、接收时间、时钟误差和受控本地文件路径。只能包含截止 received_before 已接收的帧；不得把整个未来录像交给实时执行器，不得以处理时间代替未知拍摄时间。

该端口当前不调用。ReplayAdapter 只为本地有限录像模拟这种窗口输入，经 CameraService 的设备锁与执行代次检查后交给 ReplayWorker。正式设备仍需实现会话入库、停止/取消确认、媒体连续性与时间线验证，再接入公共执行器。两款型号的真实能力保持 unknown；不能把回放通过视为 SDK 可用。
