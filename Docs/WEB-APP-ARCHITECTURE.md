# Web / iOS 共用 Agent 与设备媒体接入

更新：2026-10-14，`dongrunze`。Web 0.2 五栏应用与 iOS、Cloud 一起维护在本仓库，旧独立 Web 仓库作为历史原型参考。

## 当前结构

```text
Web React ─── /api ──┐
                      ├─ Cloud：Agent → CameraService → LiveDevices → 图片/回执
SwiftUI ───── /api ──┘                      ↑                 ↓
                                           └── 采集客户端 ───┘
Web 官方播放器 ↔ 官方媒体连接 ↔ T8171 / T8214 ↔ iOS LiveMediaPlayer
```

视频在官方 SDK 播放器中播放。Cloud 发放单次取样请求，客户端读取随后直播样本并回传，Agent 只使用请求对应的图片或视觉核验结果。设备列表、SN 映射、媒体保存与请求校验在后端统一实现。

## 仓库分工

| 目录 | 职责 |
| --- | --- |
| `EvidenceGuard/` | iOS 业务界面、APIClient、官方发现与直播页 |
| `SDK/Bridge/` | 官方 Kotlin SDK 的自有桥接；由 Mac 重新构建 SampleCore |
| `Web/` | 助手、摄像头 Skill、任务、记忆、设置；官方 Web 鉴权、直播与取帧、SDK 切换 |
| `Cloud/server/evidenceguard/camera/live.py` | 设备注册、媒体会话、取样挑战和接收适配器 |
| `Cloud/server/evidenceguard/camera/live_routes.py` | 两端共用 HTTP 协议及固定官方 OpenAPI 代理 |
| `Cloud/server/evidenceguard/camera/service.py` | 共用设备锁、执行代次、超时与持久回执 |
| `Cloud/server/evidenceguard/harness/` | 有约束工具调用与模型输入 |

先改服务端合同，再同步 Swift Codable 和 Web TypeScript。不要复制第二个 Agent 后端。CI 在同一仓库检查 Cloud、Web 与普通 iOS Simulator；官方 arm64 SDK 构建由持有资料包的 Mac 验证。

## 本轮边界

- 接入已经完成官方配网、绑定的设备；Web 手输 SN 是登记，不能代替首次绑定。
- iOS 通过发现列表同步，Web 在官方鉴权后登记已知 SN；记录归属来自受信任客户端，后端没有独立厂商所有权核验。
- 同 SN 共用一个设备 ID；每台设备同一时刻只允许一个本项目采集会话。多个客户端可共用后端结果，不等于多个 App 自动共享官方登录态或视频轨道。
- Web 已有三步 Skill 编辑、区域圈选、录像上传与回放试跑、任务管理和个人设置，复用 Cloud 的版本、来源、设备占用与人工确认校验。具体入口及接口见 [Web 功能对齐](WEB-PRODUCT-PARITY.md)。
- iOS 直播页切走/锁屏、Web 标签隐藏会停止采集，后台持续守护仍需专用执行端。
- `capturedAt=null`，`sampledAt` 是客户端取样时间，`receivedAt` 是后端接收时间；不伪造传感器时间或持续观察覆盖。
- T8214 暂按官方返回的 main/合成画面处理，不把两路镜头推定为两个独立设备。PTZ/对讲、换网、存储与历史录像另外实现和验收。
- 保留 `physicalDevicesValidated=false` 和真实 Skill 发布检查，不因收到一张图片绕过验收。
- iOS 已有可配置的 APNs；Web 仅有应用内提醒。两端个人会话和记忆按安装标识隔离，不能把共享摄像头任务误写成个人记录自动跨端同步。

## 启动与交接

Web 开发端口 5173 将 `/api` 代理到 Cloud 的 8790；构建后以 `EG_WEB_ROOT=/绝对路径/evidenceguard-ios/Web/dist` 同源托管。官方 SDK 在本地恢复，不上传 Git。团队联调使用 HTTPS 和已有团队鉴权；正式家庭用户权限尚未实现。

完整启动命令、官方参数说明、接口表、模型配置与实机验收清单见 [实时设备接入指南](LIVE-DEVICE-INTEGRATION.md)。完整目标规划见 [SDK 接入与产品补全方案](DEVICE-SDK-INTEGRATION-PLAN.md)，其中后续里程碑不能当作当前已实现能力。
