# SeedLite 图像分析与 AgentTools v0.3 接入

本次按新版 iOS 守护架构接入，产品 Web 不再扩展。Dashboard 继续提供模型、提示词版本与调用观测。本文中的“已实现”指源码及相应自动测试；不等于服务已部署、官方 iOS Framework 已重新打包或真机效果已验收。

## 1. 阅读与复现的材料

| 材料 | 核对结果 | 使用方式 |
| --- | --- | --- |
| `SeedLite_Vision_Kit_20261016_v3_handoff.zip` | ZIP SHA-256 `5a71fc5ef9c6e5ac1bb07885eb7b22fc5f44fcb0e54e18eac9f73a1b2aa113a4`；219 个清单文件校验通过 | 阅读交接说明、实验方案、提示词、验证器、运行器及两份人工复核报告 |
| `EvidenceGuard_AgentTools_Source_v0.3.0.zip` | ZIP SHA-256 `b8ead6aaae62082b32a6b5d46458b6c76b0666ab0bcb328fb59e09a97f02d3e4` | 更新 29 个工具定义、45 项能力矩阵、验证范围和原生桥接 |
| 当前仓库 | 已合并 `main@b321730`、远端 `dongrunze@b0ac6b2`；新版 `VisualScenes` / `SceneHarness`、私有录像检索、Dashboard 归档和 iOS API 传输 | 接入现有服务与执行器，不启动实验包的独立 HTTP 服务 |

交接包的 28 项离线测试已在独立环境复现通过。Windows 需启用 Python UTF-8 模式，否则部分脚本按 GBK 解码报告失败。`--sample --validate-only` 显示 1 个样例就绪、28 个业务案例待补素材；`--sample --prepare-only` 完成 DepthART 预处理，没有请求云端模型。结果来源说明见 [vision/UPSTREAM.md](../Cloud/server/evidenceguard/vision/UPSTREAM.md)。

**交接包还不是经过真机验收的连续视频理解服务。** 它固定目标，比较首尾 RGB 图片，试验 A/B/C 条件及重复调用。共享的合成样例中，真实左移仍出现 B 组向上、C 组向下偏左等误判；相对深度还出现跨帧亮度误用。28 个真实业务案例待补，未共享的实景记录无法在这里复核。结构合法、接口成功不等于方向正确。

## 2. 三条业务链路的分工

```text
iOS 官方直播 → 带请求挑战的截图 → CameraService → 不可变 Store media
                                             │
  用户需求 → 守护草稿 → 框选 → 确认 → VisualScenes 定时采样
                                             ├→ 既有 SceneHarness → 守护状态/提醒
                                             └→ 显式首尾图分析 → SeedLite B → 只读分析回执

实际导入的录像 → VideoPipeline → 1024 维联合索引/检索 → 视频复核 → 可播放证据

用户控制要求 → 已授权工具 → 确认卡 → 前台原生执行器 → 官方 App SDK
                                                  └→ ACK / 停止回执 / 人工效果复核
```

首尾图分析不替换现有守护判断，也不为每次定时采样额外调用实验模型。用户在守护详情点击“对照参考图与最近采样”，或让助手对照指定守护时，才运行单次 B 条件分析。录像向量检索继续使用其现有索引与复核链路；两张截图不会变成录像，也不会被写进视频向量库。向量接入另见 [最新架构对齐](VIDEO-MVP-LATEST-ARCHITECTURE-2026-10-17.md)。

## 3. 新增接口与源码入口

| 接口/位置 | 行为与边界 |
| --- | --- |
| `POST /api/visual-scenes/{id}/analyze` | 请求 `{revision, includeDepth:false}`；要求安装身份与私有空间凭据；只读该用户已框选守护的参考图及最近采样 |
| Agent `analyze_visual_endpoints(guard_id, revision)` | 仅新版已认证 iOS 实时守护上下文提供；本轮选定设备限制仍生效；历史回顾不获得该工具 |
| `visual_skills/service.py::analyze_endpoints` | 拒绝其他用户/设备/旧修订；禁止由模型传任意媒体 ID、路径或 URL；分析前后复查视角、修订和取消状态 |
| `vision/endpoints.py` | 每端完整 RGB + 同帧 ROI 裁剪，共 4 个图像输入；只调用一次 B 分析；返回来源、时钟含义、模型、提示词版本、限制 |
| `vision/validation.py` | 校验帧 ID、目标 ID、对应关系及证据约束；错误变为 `unknown`，不把无结果解释成正常 |
| `EvidenceGuard/APIClient.swift`、`VisualSceneView.swift` | iOS 按钮、分析摘要、取样时间和缓存提示；旧服务无可用配置时不显示入口；保留原生 SDK 入口 |
| `Cloud/dashboard/eg_dashboard/bridge.py`、`collector.py` | 发布新模块的固定提示词及 SHA-256、模型配置元数据；纳入 Dashboard 已有 `deployed_prompt` 记录 |
| `POST /api/hardware/review` | 人工填写某次操作效果；与能力授权 `/validations`、未知占用释放 `/reconcile` 分开 |

分析结果含 `readOnly=true`、`controlEligible=false`、`isLiveConclusion=false`。`completed` 只表示分析过程完成，`semanticValidation=requires_human_review` 明确保留语义复核要求。`unknown` 会给出缺帧、不同视角、时间错误、超时或模型不可用等原因。

请求不接受额外 `mediaId` 参数。缓存键包含安装身份、守护修订、ROI、设备/通道/视角/时间来源、图片摘要、模型端点与提示词哈希；缓存命中保留原分析时间，不伪装成一次新观察。单实例串行分析，最多 3 个待处理请求，排队 10 秒、分析阶段 70 秒上限；共享视觉调用配额。部署多进程时不能把单进程队列上限当成全局限流。

`captured_at` 缺失时仍为空，只能把 `sampled_at` 解释为客户端读取直播的时间。新保存帧还保留 session、request、execution epoch 和可选 decoder envelope。门铃当前的 `main` 通道不能被解释为“主摄独立原始流”，也不能从合成画面虚构同步的上下镜头。

私人分析正文及后续引用它的助手回复不进入公开 Dashboard 请求、模型正文和回复归档；固定提示词仍可检查。业务数据库中已保存的普通帧仍按既有 Dashboard 图像归档策略处理，本次没有改变整个系统的媒体公开策略。分析缓存尚无独立用户删除接口或自动 TTL；不能宣称它已满足完整数据清理产品流程。

## 4. 根据 SDK 测试更新摄像头控制

源码入口为 `hardware_tools/{gateway,routes}.py`、`hardware_tools/vendor/camera_tools`、`SDK/Bridge/Tools` 和 `EvidenceGuard/HardwareTools.swift`。导入记录见 [hardware_tools/UPSTREAM.md](../Cloud/server/evidenceguard/hardware_tools/UPSTREAM.md)。

| 能力 | 当前接入 | 仍需验证/未接入 |
| --- | --- | --- |
| T8171 云台单步 | `camera_ptz_step` 默认 `motionMode=step`；仅四个方向，保留设备及视角引用检查 | 新 iOS 桥接的物理位移、停止行为；不能填写角度或轨迹 |
| T8171 有界连续转动 | 显式 `motionMode=continuous` + `durationMs=100…1100`；开始延迟包含在窗口内；`finally` 中同方向配对停止，停止调用最多等待 2500 ms | 这不是电机角度/速度或物理停止耗时保证；断网、进程退出等仍需现场核对 |
| T8214 云台 | 不开放机械 PTZ | 不能用门铃上下双摄布局切换模拟云台 |
| T8214 双摄模式 | 从本设备运行时目录取得 `modeRef`；SDK ACK 后使旧 ROI/视角引用失效，并要求重新核对 | 不把官方测试见过的 5/9/12 写死为产品有效枚举；不循环 stop/play 试到成功，不声称取得两路独立流 |
| 设置 | 产品桥接已有 `ptzSpeed`、`microphoneEnabled`、`audioRecordEnabled`、`statusLED`；每个字段单独验证 | 音量、所有检测参数等完整目录不等于宿主已经实现；通用“设置已通过”不授权所有字段 |
| 门铃回复 | 读取设备回复目录；播放必须有已准备的有效引用 | 当前 manifest 不声明播放路线就绪；任意文本 TTS 和全双工机器人对话未接通 |
| 录制/SD 卡/云同步 | 保留能力定义；`camera_record_clip` 明确仅客户端本地短录制语义 | 产品执行器尚无短录制、SD 历史下载、自动云上传的完整实现 |
| 官方 SDK 切换 | 原生入口保留 | 本轮没有通过官方 UI 实际改变设备或补录真机验收 |

**当前最重要的缺口是原生“可用于控制的解码新帧证明”。** 现有 `onRate/onVideoInfo/onResolution` 活动回调与 `cutImage()` 不足以证明两次真实解码进度。此次不会伪造递增计数：iOS 注册 `camera_observe.ready=false`。普通实时挑战截图仍可用于守护与人工图像分析，但不能直接签发 v0.3 的控制观察引用。因此依赖 `referenceObservationId` 的 Agent PTZ/预置位链路还没有宣称可在真机上闭环。

后续需在官方原生播放器接入能够确认的解码回调或视频帧时间戳，上传 `decoderFrame`：同设备/会话、真实递增序号、前一序号、有效尺寸、播放状态和最近帧时刻。服务端只接受 `decoder_callback` 或 `video_frame_timestamp`，拒绝码率、定时器、未递增序号及超过 2 秒的新鲜度证明。不能仅改 `ready=true` 绕过这项条件。

控制申请和派发都会检查新版正在运行的守护。用户需先暂停守护；控制已发出或停止结果未知时也不能反向开启新守护。视角变化后重新取图、框选。分析中的“左移”“未看见”不会自动映射到电机指令；明确的用户控制意图仍需独立工具和确认卡。

## 5. 验证范围与四层结果

每次操作分别保留：

1. `sdkAccepted`：SDK 是否接受调用。
2. `observedEffect`：是否实际观察到效果，初值为 `unconfirmed`。
3. `artifactValidated`：文件是否做完整性检查/解码，不把 ACK 当成媒体验证。
4. `humanVerified`：是否记录了人对这次操作的核对。

工具包内官方 Android Demo 的 21 项记录属于特定平台、SDK 包与实验环境，不自动授权本产品 iOS。能力验证绑定平台、设备、SDK 版本、SDK 文件哈希、固件、适配器能力版本和操作 variant。单步通过不能放开 continuous；设置字段各自通过。固件版本未知时重新注册不复用旧证明。

人工复核与未来能力授权分开，人工复核不会把未知停止状态改为成功，也不会释放设备占用。未知控制需停止或通过现有人工恢复流程核对；云端不自动重发。

旧版本操作缺少验证范围时继续保留作历史查看，新人工复核接口返回明确的 409 过期范围错误，不借用当前执行器的 SDK/固件信息补造历史证明，也不会自动重做原操作。

## 6. 配置、构建与联调顺序

使用服务端私有环境文件配置，勿把真实密钥写进仓库：

```dotenv
EG_ENDPOINT_ENABLED=1
EG_ENDPOINT_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
EG_ENDPOINT_MODEL_ID=doubao-seed-2-1-lite-260915
EG_ENDPOINT_API_KEY=<服务端私有配置>
```

默认开关为 0。新模块的配置独立于聊天、录像复核和 embedding；不会悄悄借用其他模型密钥。此次只接 RGB B 条件；`includeDepth=true` 返回未接入。DepthART/ONNX、DIS 光流、跨镜头分析和重复 A/B/C 实验继续留在独立交接包，未给在线服务增加这些大依赖。

联调顺序：先同步并重启同版本后端 → 检查 Dashboard 的固定提示词版本 → Mac 重建包含新版四个 Tools Kotlin 文件的官方 SDK 桥接并编译 iOS → 用户前台连接设备 → 创建、框选并开启守护 → 等待至少一张后续采样 → 点击只读分析 → 核对首尾时间和未知项 → 单独完成解码证明接入及硬件诊断 → 再逐项放开 Agent 控制。

`SDK/prepare.py` 会复制 `Bridge/Tools/*.kt`，包含新 `BoundedPTZ.kt`。Windows 的真实 AAR 类型检查只能证明 Kotlin App SDK 方法/类型兼容，不能替代 iOS Framework 链接、签名、TestFlight 或电机/双摄真机验收。

发布打包会明确收集 `vision/prompts/*.md` 并计算哈希；仅复制 Python/JSON 会因缺少 `common.md` 导致启动失败。部署审计和 Web 独立发布检查同样纳入这些提示词，避免在后端提示词已经变更时误判版本一致。其他 Markdown 实验报告及私有环境文件不因此进入发布包。

回退首尾分析可将 `EG_ENDPOINT_ENABLED=0` 并重启，iOS 隐藏入口、Agent 不再获得新工具，原守护与录像检索继续使用原链路。不要为回退删除业务数据库。回退工具桥接需同步服务端与 iOS 版本；先处理仍在执行或未知的操作，恢复旧版本后重新登记和验证，不能复用新版本的能力证明。

## 7. 自动检查

新增测试使用合成图、脚本化模型和测试执行器，不冒充设备测试。覆盖来源错配、视角/修订过期、取消、队列与预算、缓存、非法模型结论、私有权限/归档、历史工具隔离、控制与守护互斥、单步/连续授权和停止回执。

```powershell
.venv/Scripts/python.exe -X utf8 -m pytest Cloud/server/tests -q
.venv/Scripts/python.exe -X utf8 -m pytest Cloud/dashboard/tests Cloud/demo_release -q
.venv/Scripts/python.exe -X utf8 SDK/typecheck_tools.py --sdk-root '<官方 AppSDKDemo 路径>'
.venv/Scripts/python.exe -X utf8 scripts/check_sdk_host.py
```

在合并后的代码上运行这些检查，并由 GitHub/macOS 继续执行 iOS 编译与兼容性测试。当前文档不将本次离线验证说成已调用真实 SeedLite 服务、已部署云端、已重新上传 TestFlight，或已完成硬件控制验收。

本机验证记录：合并后 Windows 全量 **500 项通过、10 项 POSIX 检查跳过**（后端 437、Dashboard 37、发布 26）；Linux 隔离环境后端 **447 项通过**，覆盖上述跳过项。随后追加“连续转动未返回停止回执”的兼容用例，硬件 v0.3 与发布专项 **33 项通过**。Web **23 项通过**，其中 3 项属于已有本机未提交诊断工具，其余 20 项为仓库测试；TypeScript/Vite 构建通过。官方 AAR 桥接类型检查与宿主 plist 检查通过。新增 iOS API 契约测试覆盖旧守护响应兼容、私有请求头、unknown 解码及 90 秒有界请求超时，尚待原生测试执行。

后续补查：Dashboard 图像分析分类已包含 `vision.endpoints`，在 Chromium、WebKit、mobile WebKit 的 3 项专项中均可查看模型/状态并显示私有正文说明。旧回执范围兼容加入后，硬件 v0.3 专项共 8 项通过。GitHub `ab0edcd` 的 Cloud 检查与普通 iOS 模拟器编译通过；完整端到端兼容性结果以 PR Checks 为准，不能据此认证官方 arm64 SDK 或真机。
