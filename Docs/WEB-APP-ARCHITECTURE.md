# Web / App 共用 harness

## 仓库与开发优先级

2026-10-09 起以 iOS 为主：`evidenceguard-ios` 保存 SwiftUI、Cloud 和 harness，`evidenceguard-web` 保存 React 原型。二者独立 Git / CI，Web 暂缓开发。共享的是 Cloud API，不复制第二套 Agent 后端。旧的 `evidenceguard-hackathon` 保留历史参考。

## 已有实现

```text
Web React ───── /api ──┐
                       ├─ Cloud：Agent → 受约束工具 → Skill/录像/设备调度
iOS SwiftUI ─── /api ──┘                 └─ SQLite / 证据与录像文件

Web SDK：浏览器 WebRTC → 解码裸帧联调（目前不进入正式 Worker）
App SDK：Kotlin Bridge → 设备发现 / 缩略图 / 历史事件联调（真实设备待验证）
```

两端共享任务配置、服务端能力检查、草案版本、试跑报告、执行状态和证据。Web 与 App 的对话 ID 各自保存，避免两个输入框同时发起同一段运行；任务与证据来自同一个数据库。

Web 已接上首页、Skill 列表、AI 输入/取消、按任务对话、草案圈选和保存、录像上传/播放、历史时间范围与结果卡、试跑报告、冲突后的显式切换。暂未补浏览器语音；iOS 保留现有录音转写交互。圈选使用实际图片尺寸和 0–1 坐标；空画面不能圈选，修改后必须重新保存和验收。

## SDK 能力边界

| 能力 | Web SDK 路径 | App SDK 路径 | 当前项目状态 |
| --- | --- | --- | --- |
| 直播 | `Provider` / `DeviceLiveLayout` | `LiveMediaPlayer` | Web 接入联调界面，尚无真实 Token/设备验收 |
| AI 媒体输入 | `subscribeMediaChannelFrames` | 事件触发 → 缩略图 / 录像 | Web 最小间隔 3 s；App 按官方 App SDK 文档接事件媒体，不承诺持续视频帧用于 AI |
| 录像与事件 | 收到的 Web demo 主要覆盖直播；其他能力需逐项核对版本 | 事件查询 / 事件播放器 / 下载 | Cloud 已存录像闭环可用；从设备导入待接 |
| PTZ 等控制 | 不假设 Web demo 已提供 | 按设备物模型能力 | T8171 与 T8214 的能力不能混用；待设备验收 |
| SDK 设备发现 | 真实 SN / OpenAPI 配置 | `EvidenceGuardSDKBridge` | App 增加实际设备、事件和图片查询；现场发现与媒体仍待验证 |

App 的 `OfficialSDKInspectionView` 只提供联调：从 SDK 查询已发现的赛事设备，读取设备或事件缩略图，按本机自然日查看最多 50 条事件。不上传媒体到 Cloud、不启用守护，也不提供 PTZ / 长时间直播控制。历史查询与媒体取消后丢弃迟到回执；SDK 内部网络请求可能继续结束，不能把 UI 取消当成已确认设备会话停止。

Web 使用官方资料包里的 UMD 产物与 React 18；不引入 demo 的浏览器直连 AI Key。浏览器只展示取图联调，不调用生产守护。`capturedAt` 是 SDK 回调本地时刻，`timestamp` 是媒体时间微秒；不能把两者冒充设备拍摄的绝对时间。T8214 Web 返回的可能是拼接单流，不能未经验证拆成两个独立摄像头。

Web 预览用 Web Locks 阻止同源浏览器重复打开同一 SN，但这不是全局设备锁。App 与 Web 尚未实现跨客户端会话协调，联调前要求用户停止其他客户端的同设备任务；真实任务发布保持关闭。

## 下一阶段的集成顺序

1. 验证实际账号、Token 和 SN，建立 SN → 逻辑设备/通道映射及能力回执。
2. Cloud 通过 CameraService 发放带执行代次的设备占用租约，Web / App 的所有主动设备操作受同一租约约束。断开客户端不自动声称设备已停止；迟到回执丢弃，无法确认时隔离设备。
3. Web / App 上传受限媒体窗口及真实来源元数据，Cloud 接 `OfficialSDKBridge` 接收缓存，再进入现有 Worker；服务端继续要求 Every N s、N ≥ 3。
4. App 下载实际事件录像到受控文件，再上传既有录像接口；入库后的历史分析可并行，设备下载自身仍受占用限制。
5. 完成正例/反例、遮挡、断流、恢复和停止回执验收，再允许真实 Skill 发布。

当前 `physicalDevicesValidated=false`。UI 的 SDK 就绪、文件存在、模拟器编译或回放成功均不能改变它。

## 分发

Web 和 API 当前用于本机开发。Vite 把 `/api` 代理到 8790；构建后需显式设置 `EG_WEB_ROOT=/绝对路径/EvidenceGuard-Web/dist` 才由 Cloud 同源托管。真实摄像头取流需要浏览器在线；裸帧 API 需支持相应能力的 Chrome / Edge 和安全上下文。

公开部署前需部署 HTTPS、用户身份与媒体访问控制。现有 API 为单团队本地联调，没有多租户鉴权，不能直接暴露到公网。iOS 的外部分发按 [TestFlight 流程](TESTFLIGHT.md) 准备，开发和内部真机验证可以同步进行。
