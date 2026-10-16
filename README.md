# EvidenceGuard · iOS / Cloud

## 后端 DepthART / DIS 与单步视觉控制（2026-10-17）

**已发布到 demo**：`tools-e4725de3d0d287d8`（后端源码 `a9387d2`）。发布前验证云端最新私有模型配置可调用，发布后密钥文件哈希不变；原业务记录、Web资源与team/review服务保持。本机后端/Dashboard/发布工具合并 **541通过、10跳过**；云端Linux后端 **482通过、1跳过**，独立部署路径上的真实DepthART/DIS及模型调用另行验证通过。单次模型不合规结果按unknown拒绝，不将这组烟测当作准确率或真机验收。

本轮保持 iOS / Web 前端和官方SDK桥接不变，补充有界真实帧窗口、DepthART448与DIS CPU处理、当前目标定位到单步工具的编排、SDK回执后的新图复核。助手新增 `sample_camera_vision`、`aim_camera_at_guard_target`、`read_visual_control`，继续使用现有硬件确认卡；不自动连续追踪。`EG_ENDPOINT_PROFILE=video` 显式复用云端当前有效模型配置，不尝试旧官方密钥。

**后端不能生成缺失的 iOS 解码回调。** 现有 `camera_observe.ready=false` 保留，没有原生解码证明时返回 `NATIVE_DECODER_PROOF_REQUIRED`，不能宣称已实现真机自主转动。光流也只在真实取样间隔≤1秒且视角一致时运行。实现、部署/回滚与验收范围见 [后端图像处理与控制接入](Docs/BACKEND-VISION-ROLLOUT-2026-10-17.md)；以下首版RGB描述属于早期接入记录。

## Dashboard 场景导览、图像记忆与录像索引（2026-10-17）

根据实际网站审核重整评委阅读路径。作品演示选择门口包裹、室内宠物或工作室物品后，点 **开始逐步演示**：需求 → 选框 → 确认 → 基线 → 条件变化 → 遮挡 → 提醒与追问。可重新开始；重新开始只重置网页示例，同摄像头的另一示例暂停。手机可适应窗口或放大。宠物/工作室缺少成对采样照片的状态使用明确标记的示意图，不把同一张照片解释成相反事实。

**图像记忆与分析**分成视觉证据、完整图片台账、模型调用三个入口；“图像记忆”指有来源与时间的已保存视觉观察，不等同个人文字偏好。**视频向量库**先显示真实入库录像，再按时间窗口组织视频向量与图像关键帧，点击可定位原片。采集器只从已发布索引的对应文件复制真实关键帧，拒绝私有查询图、越界路径和符号链接。建库调用与查询调用分组；私有检索展示实际诊断状态，正文继续留在授权 App 内。总览增加图像/录像直达入口，切菜单回到页首。

本轮不改摄像头控制、iOS 业务代码、模型配置或既有私有查询策略。操作方法、修复前截图索引、数据核对和验证范围见 [Dashboard 体验审查](Docs/DASHBOARD-UX-AUDIT-2026-10-17.md)。公网部署结果以该文档后续验收记录为准；静态 ZIP 不包含真实录像、账号或业务数据。

## 真机录像检索、iOS 导入与 demo 发布（2026-10-17）

已保留并合并 `main@b321730` 和 `dongrunze@80438af` 的最新守护、SeedLite、v0.3 工具、归档及演示修复。**demo 现在已部署图文视频检索 v2 和合并后的 Cloud 模块**，原 Web 资源、账号配置、数据库及团队/评审服务保留。以下早期记录中的“未部署”描述当时状态；本次没有生成或上传新的 TestFlight。

使用官方 Android SDK 保存的 T8171 真机录像完成验收：取前 65 秒建立 **4 个视频窗口 + 12 个关键帧、1024 维向量**。实际模型为 `doubao-embedding-vision-251215` / `doubao-seed-2-1-lite-260915`；文字查询放入约 **37 秒**、拿走约 **51 秒**，图文查询拿走约 **51.5 秒**，图片查询能找到水瓶；“猫经过”没有已核验匹配。云端 Agent 的历史模式实际调用 `search_recordings`，返回约 **00:51** 的可回看片段，没有调用现场取图或控制工具。完整结果也记录了空场高相似度、模型误描述和未核验候选，不能把这一次样片称为准确率评测。

iOS 新入口：**设备 → 录像库 → 从设备事件下载录像**。查询官方事件、选择一条已有录像的事件，经确认后暂停直播并排空工具执行，使用官方 `EventMediaPlayer.startDownload` 下载到手机，再调用现有上传/索引接口。支持取消、超时、上传失败后在当前页重试，保留设备原片；不扫描全部连续 SD 录像、不承诺后台自动同步。证据详情新增 **用这张画面查历史录像**，带来源摄像头和参考图进入现有图文检索。官方 SDK 工作区继续保留。**这些 iOS 改动仍需重新生成 Framework、编译并在 iPhone 验证；Android 录像验收不能替代该步骤。**

修复真实上传中发现的状态接口问题：转码尚未生成可播放文件时，`GET /api/recordings/{id}` 仍返回排队/索引状态，不再误报 404。合并版 Linux 后端 **453 项通过**；Windows **443 通过、10 项 POSIX 检查跳过**；发布检查 **30 项通过**；本机四种浏览器 **200 通过、8 跳过**，TypeScript / Vite 通过。Mac CI 与 arm64 真机结果单列，不以这些测试替代。部署摘要、回滚命令、查询实测和 Mac 验收步骤见 [真机录像接入与验收记录](Docs/VIDEO-HARDWARE-ACCEPTANCE-2026-10-17.md)。

产品代码 `246ab88` 的 [PR CI](https://github.com/zhangmiao03/evidenceguard-ios/actions/runs/38954320983) 四项检查全部通过：普通 iOS 模拟器编译、**5 项界面 + 12 项 API 测试**；Linux 四浏览器 **204 通过、4 跳过**；macOS WebKit **102 通过、2 跳过**。跳过项均需要未公开的官方 Web 构件。诊断上报改为 utility 调度，测试结束前先关闭上报入口并排空请求，避免失效连接被迟到任务使用。此后仅补充验收文档及 Firefox 普通 HTTP 测试的键盘表单提交，四浏览器各重复 3 次共 **12 通过**；最新检查状态见 PR。上述编译不包含官方 arm64 SDK，仍需 Mac/iPhone 完成设备事件下载验收。

## 作品演示同步新版 iOS（2026-10-17）

Dashboard 的[作品演示](https://demo.47.131.21.137.sslip.io/dashboard?view=showcase)已按最新 GitHub main 的 iOS 1.0(17) 前端重做：**助手 / 摄像头守护 / 设备 / 记忆 / 我的**，复用 anker 头像与蓝白渐变，详情页隐藏底栏。守护走“说需求 → 获取并框选画面 → 确认开启”，暂停清除旧选框；新增现场/历史范围、文字/参考图检索、蓝牙连接确认示例、临时记忆管理，以及“我的 → 设置 → 摄像头调试”。另已同步 `dongrunze@d584dd3` 新增的首尾图核对入口，网页明确显示脚本示例和缓存说明。

全部为明确标记的浏览器本地脚本；真实模型、图片、最终回复和 Trace 仍在监控页读取。网页不连接硬件、不申请蓝牙/麦克风权限、不写业务数据。本轮只更新 Dashboard 前端和网站下载包，不重新发布 iOS、替换 Agent 业务代码或重启摄像头后端。源码映射、操作与验证见 [iOS 演示同步说明](Docs/IOS-SHOWCASE-SYNC.md)。

## SeedLite 首尾图分析与硬件工具 v0.3（2026-10-17）

已整合 `main@b321730` 与远端 `dongrunze` 的检索、图片/回复归档修复。新版 iOS 守护详情增加“对照参考图与最近采样”；助手通过 `analyze_visual_endpoints` 调用同一只读服务。读取当前用户已框选守护的两张已保存图片，单次运行 SeedLite RGB B 条件，并保留来源时间、未知项和缓存说明。它不会把截图生成录像索引，也不替换原有持续守护提醒。

`EG_ENDPOINT_ENABLED` 默认关闭，启用需单独配置 `EG_ENDPOINT_BASE_URL / MODEL_ID / API_KEY`。Dashboard 可检查固定提示词版本与哈希，私人分析正文及同对话后续引用不会进入公开回复归档。发布包已包含运行时 Markdown 提示词，提示词改动也纳入发布一致性检查。

AgentTools 升级到 v0.3：区分云台单步/有界连续转动及设置字段的验证，连续运动配对停止；SDK 接受、实际效果、文件校验、人工复核分别记录。新版守护与硬件控制互斥，未知停止结果保留占用。**现有 iOS 活动回调尚未提供 v0.3 所需的解码进度证明，依赖新帧引用的 Agent PTZ 尚待接通真机闭环。** 不以计时器、码率或截图成功伪造该证明，也不把模型图像方向直接转换成电机动作。T8214 双摄模式使用设备返回的目录，保留官方 SDK 工作区。

交接包 219 个文件哈希校验、28 项离线测试和样例预处理已复现；本轮没有调用真实 SeedLite 云服务、部署此模块或上传新 TestFlight。后端、Dashboard、打包和回退测试已执行，原生 SDK Kotlin 桥接通过实际 Android AAR 类型检查；iOS 编译、Framework 打包及物理效果仍需 Mac/真机验证。详细接口、缺口、启用步骤和回退见 [SeedLite 与 AgentTools 接入说明](Docs/SEEDLITE-AGENT-INTEGRATION-2026-10-17.md)。

## 最新 main 与向量 MVP 接入（2026-10-17）

已同步 `main@2a4fd0c`（含 `3c82719`）的原生摄像头守护、前台单路连接、设备页、报告改进及原生测试身份注入，并整合 `dongrunze@3f7a591`（含 `0c62cbf`）的图片/回复归档、历史步骤上下文与显示摘要回执。新版 iOS 导航为 **助手 / 摄像头守护 / 设备 / 记忆 / 我的**，旧任务在“摄像头守护 → 全部关注事项与历史任务”。本次是源码整合；没有部署业务服务或上传新的 TestFlight 构建。

向量 MVP 继续复用 Cloud `VideoService`，可从 **设备 → 录像库 → 用文字或图片检索录像**，或助手的历史对话菜单进入。`guardFlowVersion` 与 `referenceImageId` 同时保留，历史查询不会获得实时守护创建工具；纯文字和带图 Agent 检索都归属当前已识别的客户端。候选、核验和原片定位复用同一套服务；实时守护的离散图片不会自动成为录像索引。

目前最快的真实联调方式是手动导入设备导出的短录像，完成 v2 索引后验证文字 / 图片 / 图文查询，再接官方 SDK 的录像下载与上传协调器。**SD 卡录像自动同步、从守护卡一键以图查历史仍待开发**；多台设备的历史检索不等于多路实时播放。原生官方 SDK 调试入口保留，产品 Web 继续保持原功能范围。

完整的数据流、接口状态、模型与索引复用、源码定位、阶段验收及回退边界见 [向量 MVP 与最新架构接入分析](Docs/VIDEO-MVP-LATEST-ARCHITECTURE-2026-10-17.md)。下方保留各次实现与发布记录，以各次日期和验证范围区分。

本轮在固定源码快照和隔离数据库上验证：Linux 后端 **418 项通过**；Windows **408 项通过、10 项 POSIX 专用检查跳过**（已由 Linux 覆盖）；Dashboard **37 项**、发布检查 **24 项**、Web 单元 **20 项**通过，TypeScript 与生产构建通过。图片归档和媒体预览在 Playwright Chromium / Firefox / WebKit / mobile WebKit 共 **12 项通过**。两个 iOS target 的新页面引用及 SDK 宿主配置检查通过；新增原生 APIClient 契约测试已随源码交付，**本机未运行 Xcode / SwiftUI 编译或真机测试**。

## 当前演示路线（2026-10-16）

根据团队最新决定，比赛演示与后续硬件开发集中在 **原生 iOS App + 官方 App SDK + Cloud Agent**。当前官方 Web SDK 的硬件能力不足以覆盖演示需求，产品 Web 停止功能扩展，不再要求与 iOS 同步补齐功能或作为比赛演示验收端。下方 Web 功能、测试和部署内容保留为历史实现与排查参考。

后续优先验证 iOS 真实设备连接、实时取流与按需抓拍、T8171 云台、T8214 双摄模式，以及设备录像下载到手机后上传 Cloud 的链路；后者尚未实现自动同步。保留 iOS 官方 SDK 工作区切换，用于配网、绑定、完整设置和能力对照。SDK 回执、静态类型检查与既有普通 iOS 构建均不能替代当前桥接版本的真机验收。

现有 `Web/` 源码、官方 Web Demo 和已部署入口保留，不在此次路线调整中删除或下线。Cloud API、Agent 和供团队排查使用的 Dashboard 继续服务 iOS 开发；Dashboard 不承担摄像头硬件演示端职责。本次只调整开发范围，不修改运行时路由、鉴权、媒体占用规则或部署配置。

**硬件边界（团队确认）：所有摄像头控制统一由手机 App 的官方 SDK 执行。** Dashboard 的手机外观是交互展示，不具备手机 SDK 的硬件接口，不能用 Web 模拟 App 来完成配网、绑定、云台、对讲等控制。云端 Agent 可分析手机上传的画面并记录任务与回执；后端已有工具定义或控制意图不等于具备独立直控摄像头的能力。后续 Dashboard 扩展集中于运行监控、证据、模型与提示词、检索及服务器资源。

## 视频检索 MVP v2（2026-10-16）

按团队最新设计接入 **文字 / 图片 / 图文联合检索**。iOS 可从“录像库 → 用文字或图片检索录像”或历史对话菜单进入，支持选图、可选裁剪、摄像头/时间范围、先显示候选再更新核验、原片定位，以及保留原参考图继续问助手。旧云端通过 `videoModels.retrievalVersion` 门控，不把新界面误报为已部署。

Cloud 新增视频 + 关键帧双索引、1024 维 float32 二进制存储、原子发布与失败续建、SQL 范围过滤、NumPy 分块召回、64 MiB 上限矩阵缓存、RRF 融合及后台核验。新接口为 `/api/video-search-images`、`/api/video-search` 及对应查询/缩略图接口；Agent 的 `search_recordings` 使用同一服务。参考图绑定经过私有凭据证明的安装实例，不导出到公开 Dashboard；原录像仍按现有团队服务隔离。产品 Web 不增加新检索界面。

已调用真实网关检查四类 Embedding 输入，并在隔离数据库完成合成 MP4 三种查询。云端 1 万合成向量的热召回 P95 约 **75 ms**（30 次、单 BLAS 线程、39.06 MiB 向量缓存）。这些不是家庭真实录像的准确率结果：1–2 小时录像 / 60 条留出查询、Mac 编译和新版 iPhone 交互仍待验收，SD 卡录像自动下载也尚未接通。本轮没有替换运行中的 demo 或上传 TestFlight。

升级需安装新 `Cloud/server/requirements.txt`，提供 FFmpeg/ffprobe，并为旧录像重新建 v2 索引。`EG_VIDEO_INDEX_V2=0` 可保留旧文字链路；旧表与索引保留。完整的接口、边界、实测失败与修复、评测脚本和回退步骤见 [视频检索 MVP v2 实现记录](Docs/VIDEO-SEARCH-MVP-v2-2026-10-16.md)。

## 最新 iOS 与硬件桥接整合（2026-10-16）

`dongrunze` 已继续整合 `feat/anker-assistant@1ba73c5`（含先前 `ce8204d`），保留 `dongrunze@3830298` 的硬件工具、Token 直连、门铃双摄说明及云端兼容修复。当前 `main@cc16c98` 已在两分支历史中。iOS 接入助手持久时间线、聊天记忆开关与失败重试、早晚报告、外部应用连接及摄像头观察授权；现有 Web 保留原功能，未引入该特性分支的新增产品界面。

官方原版入口现为 **我的 → 设置 → 摄像头调试 → 打开官方设备调试页**。日常导入已绑定设备使用“摄像头 Skill → 连接摄像头”或“我的 → 连接摄像头”。修复 Compose 宿主配置，进入前检查框架及资源，归档/导出也检查安装包；内部构建可从私有 xcconfig 预置联调账号。仓库不包含真实账号、Token 或 SDK 二进制。

硬件桥接对齐官方示例：T8214 使用 `changeVideoMode(mode, 0)` 原位切换合成画面，保留 SDK 原始重启标记但不主动重建媒体会话；切换后仍须新画面验证。T8171 单步停止带原方向，预置位跳转没有已验证的停止路线时返回 `STOP_UNVERIFIED`。云端保留未知结果和设备占用，迟到的执行回执也不会改成成功或重新验证中，须人工核对后释放。

本次源码整合不更新云端部署或 TestFlight。当前验证结果和 Mac 交接步骤见 [整合验收记录](Docs/verification/ios-branch-integration-2026-10-16.txt)。重新运行 `SDK/prepare.py` 生成桥接后，才可在 Mac 验证 `EvidenceGuardSDK` 的 arm64 构建及两款真机；旧 IPA 不能验收本轮改动。

## 图片台账、历史回复与显示校验（2026-10-17）

`/dashboard?view=images` 新增直接读取业务 `media` 表的全量分页台账，分别统计记录数、不同内容数及可预览记录；不再把事件页的部分图片当作全部存图。每条图片标注取样来源和时间，可按同一字节摘要查看仍保留的模型输入链路。预览副本共享 160 MB 预算，超限会明确标注；业务原图不被该缓存删除。

`/dashboard?view=traces` 新增历史最终回复，从业务库回查正文，区分“已保存 / 有客户端展示回执 / 正文摘要一致”。缺失历史步骤不会补造。两类台账支持全局筛选、游标分页和筛选范围的全量 JSONL 导出；旧快照 JSON 的离线导入继续保留。匿名页面不公开私有参考图及其回复，正文按有效服务密钥再脱敏。

关键模型、提示词、工具、最终回复及显示回执单独保留，默认上限 10,000 条 / 128 MB，按最旧任务整组淘汰，与 20,000 条一般诊断记录分开。迁移只保留尚存的真实记录，不能恢复已经删除的历史。

iOS 新增 `POST /api/ops/display-receipts`：只发送 UTF-8 SHA-256、转换版本和 App build；后台独立诊断传输不阻塞回复或取流。最终正文变化会重新上报。旧版仍显示“缺少文字校验”；新 App 必须经 Mac 编译安装后才能产生新回执，WebKit 页面测试不等于 iOS Simulator 验收。部署与核查见 [全量台账说明](Docs/DASHBOARD-ARCHIVE.md)。

## 比赛网站：iOS 交互展示、图片分析与视频向量库（2026-10-16）

Dashboard 监控页面按评委阅读顺序更新为“先看作品与链路 / 看证据与效果 / 看实现与运行”。从[运行总览](https://demo.47.131.21.137.sslip.io/dashboard?view=overview)读取任务需求与最终结果，再进入[Agent Loop](https://demo.47.131.21.137.sslip.io/dashboard?view=agent&environment=review)点击结构节点、逐步回放模型与工具记录。所有提示词、模型输入输出、工具参数与回执、最终回复仍可展开；长编号与源码指纹收进技术详情。任务列表排除接口轮询，HTTP 调用成功不等于任务成功或识别正确。

设备页展示手机 SDK → 上传 → Agent 的边界；Skill 使用状态看板，证据使用媒体卡片，服务器使用资源仪表与环境卡片，部署使用三项源码核对。原作品演示与原生 App 保持原功能。新增分享参数 `environment=demo|team|review`，页面切换保留环境；没有跨环境拼接数据。详见[评委阅读与验收说明](Docs/DASHBOARD-JUDGE-READING.md)。

作品入口：**https://demo.47.131.21.137.sslip.io/dashboard?view=showcase**。这是完整网站中的浏览器交互展示，可切换门口包裹、室内宠物、工作室场景，体验助手、摄像头 Skill、任务证据、记忆和设置；明确标注示例数据，不冒充原生 iOS 模拟器或真实硬件。监控入口为同域 `/dashboard`，继续免登录只读。使用带域名的 HTTPS 入口，不将 IP 直接改成 HTTPS。

新增 `/dashboard?view=images` 读取实际 SDK 事件视觉核验、证据结果、视觉缓存和模型调用；`?view=vectors` 读取实际录像、片段、向量维度/范数/前 16 维、模型及签名兼容状态。合成测试录像保留 `synthetic_review` 来源；数据库快照不是历史调用回放，缺少记录不算成功。按比赛展示要求，记录关联的媒体副本通过独立只读缓存预览与下载；密钥、外部签名地址和源文件路径不公开。

已修复不同入口看到空数据的问题：HTTPS 的 `/dashboard/api/*` 曾进入 App 鉴权服务返回 401；现在 demo/team/review 的 Dashboard 路径均代理至独立只读服务，原 `/api` 鉴权保留。页面增加明确错误、限时读取、自动重连、环境切换清理筛选和手动清除筛选。

完整网站 ZIP：**https://demo.47.131.21.137.sslip.io/dashboard/downloads/evidenceguard-website.zip**。解压后上传整个目录到网站根目录；静态托管能运行 iOS 演示和离线 JSON 导入，实时监控需要同源 `/dashboard/api` 后端。构建、部署、来源与验收见 [比赛网站发布说明](Docs/COMPETITION-WEBSITE.md)。

## demo 工具链发布与云端代码对齐（2026-10-15～16）

产品 Web：**https://demo.47.131.21.137.sslip.io/**，使用现有 demo 团队访问令牌；公开监控仍是 **http://47.131.21.137/dashboard**。10 月 15 日已把缺少的工具 Runtime、事件与前台取帧接口部署到 demo，并同源托管产品 Web、官方浏览器 SDK 和原版 Demo。保留云端已有记忆、定时观察、OAuth/私有安装校验、通知修复及全部业务数据；team/review 未部署。

10 月 16 日复核发现 demo 后续已切换 Codex 执行器与早晚报告版本。`main` 仍为 `cc16c98`；这些运行时改动能匹配 `feat/anker-assistant@2cc803e`。本分支同步相关后端源文件，保留硬件工具及测试，不用旧包覆盖后续发布。聊天/主动评估可用正式 Codex App Server 驱动豆包，记忆提取和视觉仍走各自接口，配置与限制见 [云端执行器](Docs/CODEX-CLOUD.md)。

iOS/Web 已有自动记忆开关、来源原话和失败重试；旧服务器未提供该字段时隐藏入口。无图设备事件显示“仅设备报告，暂无可核验图片”。上方本次合并后，iOS 支持早晚报告并保留旧服务的单时段兼容；现有 Web 仍提供单次每日概况，保存时只提交可编辑的旧字段，避免隐藏的早晚报告字段覆盖关闭操作。两端官方 SDK 切换保留。

10 月 16 日 13:35（新加坡时间）已发布最终 Web 包 `tools-3c13da608c1867d8`，包含同分支 AWS 连接与 Dashboard 查看修复，保留 `briefings-20261015` 后端及其新观察器。iOS/Web 的真实 HTTP 请求均通过当前 Codex 执行器完成两步只读工具与回复；这不是原生 App 或摄像头真机验收，Codex 子进程的模型 HTTP 次数当时未被 Python observer 直接观测。

Linux 隔离环境 **306 项后端测试通过**，包括 Windows 上曾跳过的 Codex 子进程测试；数据库副本迁移检查通过。发布/回滚/联调判据另有 24 项、监控模块 18 项、Web 单元 14 项通过。完整四浏览器回归累计 128 项通过、4 项 Windows WebKit 视频解码跳过；最新记忆/报告兼容专项 8 项、合并 Dashboard 后的受影响页面 10 项通过。生产构建及最终四浏览器公网入口/官方 SDK 切换检查通过。共享 Kotlin 对官方 Android AAR 的类型检查通过，不能替代 iOS arm64 链接或真机验收。

完整逐文件差异、发布哈希、私有备份路径、复现命令及当前验证边界见 [demo 发布与联调记录](Docs/DEMO-TOOLCHAIN-DEPLOYMENT.md)。**旧部署备份不能直接回滚后续 Codex/早晚报告版本**；脚本检查真实 ExecStart 与后续 drop-in，发现已换运行版本会拒绝覆盖。Mac/Xcode、真实摄像头和门铃、实际取流/控制、锁屏和网络切换仍须分别验收。

提交 `932451c` 的 [GitHub Checks](https://github.com/zhangmiao03/evidenceguard-ios/actions/runs/38856958726) 已核实：四个 job 都因账户付款/消费额度限制未启动，步骤数为 0；不能作为 iOS 编译通过或测试失败的证据。上方通过结果来自本地及 demo 隔离验证。恢复账户额度后可重跑，Mac 仍按交接文档独立验收。

## 当前版本（2026-10-17）

原生 iOS 以「助手 / 摄像头守护 / 设备 / 记忆 / 我的」为主线。普通问答、主动提醒和早晚报告进入同一主对话；通过一句话描述、框选和确认创建 Visual Skill。支持指定区域人员进入、框选人物离开、宠物与物品状态观察；遮挡或证据不足时保留未确认状态，不做实名或跨摄像头身份识别。

App 前台共用一路隐藏的官方摄像头连接供助手取图，可切换摄像头；不需要先打开直播页。设备页提供 Core Bluetooth 扫描与连接。早晚报告结合该时段已保存的图片讲清可见情况。锁屏持续采集、所有蓝牙产品的专有控制协议及人物真实进出提醒仍需各自验收。

**1.0 (17)** 已于 2026-10-17 分发到既有 EvidenceGuard Internal，App Store Connect 显示“正在测试”。源码验证：374 项后端测试、14 项 Web 单元测试、Web 生产构建、移动端契约检查通过。真实 SDK Release 归档、签名与 Apple 上传已通过；发布结果与 CI 限制见 [本次版本记录](Docs/verification/release17-2026-10-17.md)。下方按日期保留历史交付记录，较早的构建号与界面说明不代表当前状态。

公开仓库包含自有 App、Web、Cloud、桥接源码和测试。官方 SDK 二进制、模型服务密钥、联调账号、签名材料、运行数据及内部安装包均不在 Git 中。普通模拟器开发可从 `EvidenceGuard.xcodeproj` 开始；真实摄像头方案需自行取得厂商 SDK，并按下方开发启动说明恢复本地依赖和私有配置。

## 比赛云端 Dashboard 与服务器快捷连接

云端只读入口：**http://47.131.21.137/dashboard**，按比赛要求免登录。可切换 demo / team / review，查看真实模型调用、系统提示词、工具执行循环、Trace、部署 Python 文件与仓库基准的差异，以及每 5 秒采样的 CPU / 内存 / 磁盘 / 网络和后端进程。原有 App API、摄像头取流与媒体鉴权保持原配置；公开页面只读取脱敏快照。

Dashboard 已增加正文模式：部署 `--capture-content` 后的新记录可以直接查看每轮提示词、模型输入输出、工具参数与返回值、最终 App 回复，并导出 JSON。密钥在写库前过滤，媒体二进制和模型内部推理不显示；旧摘要不会补造正文，达到上限会明确标注。部署脚本保留服务器当前业务 release 和参数，先在实际代码上验证兼容，再逐套重启观察器。详见 [正文采集与部署边界](Docs/CLOUD-DASHBOARD.md)。

新版后端使用 Codex App Server 时，Dashboard 还记录主程序提供的上下文、实际 `thread/start` 指令与工具定义、`turn/start` 输入、工具回执和执行器返回文本。界面区分 HTTP 请求与 Codex 执行步骤；Codex 内部 HTTP、内置提示词不可见，用量更新按快照查看，不与 HTTP Token 重复相加。采集失败、模型错误与取消均不增加重试或改变原业务返回。

本机 PowerShell 在仓库根目录执行 `.\scripts\cloud_session.ps1` 可直接进入服务器 SSM 终端，不必每次经过 AWS 控制台；临时登录过期时执行 `.\scripts\cloud_session.ps1 -Action login`。`-Action status` 查询当前公网 IP 与 SSM 状态；Windows 脚本自动继承已启用的系统 HTTP/HTTPS 代理，显式代理环境变量优先，不修改系统设置。维护命令可用 `python scripts/cloud_command.py --file YOUR_SCRIPT`。2026-10-16 已重新验证新加坡实例仍为 `47.131.21.137`。安装、接口、数据边界、两套部署兼容策略、真实模型验证和回滚见 [云端 Dashboard 与快捷连接](Docs/CLOUD-DASHBOARD.md)。

## 工具链接入（2026-10-15 · dongrunze）

已合入 `main@cc16c98`，保留 iOS 埋点会话隔离与回归修复。团队 v0.2.0 工具包现在通过现有 Cloud 的 `/api/hardware/*` 接入：iOS 前台执行器领取已确认的 SDK 命令、回传结果并独立处理 stop；观察共用现有直播 challenge，图片进入产品证据库与 Agent 视觉链路。Web 补齐仅事件设备、事件筛选与核验状态，并增加工具检查、跨端确认和执行回执；官方 SDK 原版切换保留。

首次使用在“摄像头 Skill → 硬件工具与执行回执”做人工诊断，再按设备和适配版本记录真机结果；控制仍需逐次确认。Web 自身只登记观察路线，其他已接入工具可委派给在线 iOS。**SDK 回执不等于物理效果通过，包内 29 个工具定义也不等于 29 项已完成能力。** 对讲、录像导出和回复播放等尚未闭环的路线继续关闭。

Mac 必须重新运行 `SDK/prepare.py` 生成含工具桥接的 SampleCore 与真实 iOS SDK 构件指纹；普通 Simulator 不能验证官方 arm64 链接或实际摄像头。具体接入、12 项新 API、使用步骤、状态/权限约束与测试入口见 [硬件工具接入说明](Docs/HARDWARE-TOOLS-INTEGRATION.md)。本地后端 230 项、Web 单元 11 项通过，四浏览器 124 项通过 / 4 项媒体解码跳过，最后回执重传修改另通过 8 项专项回归；Web 生产构建及共享 Kotlin 对官方 Android AAR 的类型检查通过。iOS 编译与真实设备验收仍需 Mac；下方旧构建结果不能替代本轮验收。

## 本地研发 Dashboard（dongrunze）

新增参考 AIBuddy 的 `/dashboard`：运行总览、设备与取流、Trace、模型调用、提示词、任务、证据、试跑、用量与离线数据。可在没有云端/root 权限时本地运行，导入/导出版本化 JSON；模拟样例需要手动载入且持续标识。iOS、Web 和后端新增关联埋点，官方 SDK 切换与 App 五栏功能保留。

先在 `Web` 执行 `npm ci`、`npm run build`，回仓库根目录用已安装 Cloud 依赖的 Python 执行 `scripts/run_dashboard.py`，打开 **http://127.0.0.1:8790/dashboard**。Windows 例如 `.venv/Scripts/python.exe scripts/run_dashboard.py`；macOS/Linux 使用自己的虚拟环境 Python 路径。默认使用隔离的 `Cloud/data/local-dashboard/`，不读取生产环境文件。

追踪默认不影响已有服务：现有后端需显式设置 `EG_OPS_ENABLED=1` 才采集。默认提示词动态内容仅存摘要；需要全文时用启动器 `--capture-content`。独立 Dashboard 访问权限、采集口径、模型覆盖、导入格式和完整操作见 [Dashboard 开发与使用说明](Docs/DASHBOARD.md)。

iOS 埋点使用独立、限流的 URLSession，避免慢埋点请求占用业务会话；超时或失败直接放弃。macOS CI 除原有界面测试外，增加真实 APIClient 的网络故障回归，验证直播心跳、取样上传、停止、旧服务兼容与原有错误处理；后端还覆盖追踪队列满、写库失败时的画面→Agent 链路。模拟器检查不包含主办方 arm64 SDK 真机播放验收。

Actions 暂不可用时，由 Mac 队友按 [iOS 验证交接](Docs/IOS-MAC-VERIFICATION.md) 检出固定提交、运行完整测试并回传日志与 `.xcresult`。当前 `6ed031b` 的两项测试等待修正仍待复验，不能仅凭编译通过宣布全部回归通过。

本仓库维护原生 iOS App、响应式 Web App 和共用的 Cloud Agent。两端都提供助手、摄像头 Skill、任务、记忆与设置；设备、实时取帧、观察回执和媒体统一经过同一套 API，两端分别使用主办方原生 SDK 与 Web SDK 播放视频。当前接入与 Web 功能在 `dongrunze` 分支开发。

- [iOS 主仓库](https://github.com/zhangmiao03/evidenceguard-ios)
- [此前独立 Web 原型](https://github.com/zhangmiao03/evidenceguard-web)：历史参考；本轮 Web 实现在本仓库 `Web/`。
- [此前合并仓库](https://github.com/zhangmiao03/evidenceguard-hackathon)：保留原来的历史参考。
- [服务器访问与团队协作](Docs/SERVER-ACCESS.md)：已验证的 SSM 会话入口、团队授权、SSH 备用连接、新加坡三个后端环境与迁移状态。
- [深度与光流实测、复现工具和模型](Docs/VISION-RESOURCE-BENCHMARK.md)：本机 CPU/内存限额实验，三份 ONNX 权重通过 Git LFS 获取。
- [团队拉取与开发](CONTRIBUTING.md)：开发环境、分支流程、模型配置和提交前检查。
- [手机通知与提醒](Docs/APNS.md)：APNs、自动保存、投递策略和已验证范围。
- [Web 五栏功能与验收](Docs/WEB-PRODUCT-PARITY.md)：新版 iOS 功能对齐、前后端接口、浏览器差异与团队联调。

## 当前进度

2026-10-15 · **联合整合**：整合官方事件同步、iOS/Web 前台直播、新画面工具与五栏框架；同一 SDK 设备统一身份，事件缩略图不能代替新画面回执。正常来源为空设备起步，历史合成资料保留但不混入。助手保留自然简短表达，模型继续统一豆包系列。209 项 Cloud 测试、7 项 Swift 契约、9 项 Web 协议/数据检查、类型/生产构建，以及 Simulator 和重新编译 Kotlin 桥接后的真实 SDK arm64 本地构建通过；界面和浏览器验证单独记录。真实设备验证仍待赛事硬件和凭证。

**分发节奏**：先完成框架与联调，用户明确要求分发后再上传并加入测试组。build 9 已于 21:32 上传，但未加入内部或外部组；当前内部可更新的是 `1.0 (8)`。本轮后续只做代码整合与本地验证。

2026-10-14 · **提示词与接口说明同步**：普通助手与主动评估共用新版 iOS/Web 产品入口说明，修复 Web 编辑能力、草案回复入口、提醒保存方式、APNs/Web Push 差异和固定设备 ID 的过期描述。图片核验同时适用于事件图、前台直播取样与合成样本；更新缓存版本，保留原有调用额度。补齐 OpenAPI 的草案、设备登记、帧时间、预留规则与发布门禁说明，并修复多方法路由重复的 operationId。现有 HTTP 路径、请求字段及设备/任务权限保持兼容；真机发布仍未开放。检查范围见 [提示词与接口同步](Docs/WEB-PRODUCT-PARITY.md#提示词与接口说明同步)。

本次本地验证：Python 3.12 与仓库固定依赖下 Cloud **189 项通过**（新增 7 个提示词/回执/缓存回归用例）；Web 协议 **4 项通过**，TypeScript 与生产构建通过。测试核对模型请求与业务约束，未调用外部模型评估回答质量，也不代表真实设备或新 TestFlight 已验收。

此前 Web 0.2 功能提交为 `fc0243b`。[该提交 GitHub Checks 四项全部成功](https://github.com/zhangmiao03/evidenceguard-ios/actions/runs/38552925223)：Cloud 182 项、Linux 浏览器 100 项、macOS WebKit 50 项、iOS 界面 3 项，以及生产构建与 Swift 契约检查。CI 的 6 项跳过均为未恢复专有 Demo 文件的检查，和本机 WebKit 的逐帧 API 跳过原因不同。下方保留此前同步与发布记录。

2026-10-14 · **Web 0.2 五栏功能对齐**：助手支持主会话、独立话题、草稿恢复、只读历史查询与主动提醒；摄像头 Skill 保留设备接入、实时取流、新图回传和官方 SDK 切换，并加入圈选编辑与录像库；任务支持状态筛选、暂停 / 恢复 / 停止、回放试跑、人工验收和设备占用确认；记忆支持长期 / 24 小时记录；设置支持提醒时间、免打扰、时区与连接管理。后端新增幂等主会话初始化接口，兼容既有 iOS 绑定。Cloud 与 Web 必须一起更新。后端 182 项、Web 协议 4 项、本机跨浏览器 152 项通过，另有 4 项因 Windows WebKit 缺少逐帧 API 跳过；类型检查与生产构建通过。测试范围和平台限制见 [Web 0.2 验收](Docs/WEB-PRODUCT-PARITY.md)。本次提交源码，未部署或上传 TestFlight。

2026-10-14 · 同步主分支：`dongrunze` 合入 `main` 的 `0959463`，合并提交 `60ca514`。保留新的“助手 / 摄像头 Skill / 任务 / 记忆 / 我的”五栏、APNs 和自动保存提醒设置，并整合实时设备接入、Agent 新画面采集、Web 与官方 SDK 工作区。AppDelegate 同时处理推送与播放器旋转；官方工作区内点开的通知会保留，返回并释放完成后再进入助手。合并后后端 179 项、Web 协议 4 项、Linux 浏览器 48 项、macOS WebKit 24 项、原生 UI 3 项及 Swift 契约检查通过，iOS 编译与 Web 构建通过。跳过项和实机边界见 [Web / iOS 兼容性复审](Docs/WEB-IOS-COMPATIBILITY-REVIEW.md)。本次是源码同步，未部署或上传 TestFlight。

2026-10-14 · 合并前源码复审与兼容性回归：修复快速重连/退出时的释放、iOS 离页取消 Agent、Web 存储受限白屏、HTTPS 凭证保护、逐帧降级与手机退出入口。后端 163 项、本地浏览器 74 项、Linux 浏览器 48 项、macOS WebKit 24 项和原生 Simulator UI 2 项通过，普通 iOS 编译通过。跳过原因、官方 arm64 待验收项，以及此次已处理的 8 个合并冲突见 [Web / iOS 兼容性复审](Docs/WEB-IOS-COMPATIBILITY-REVIEW.md)。本次没有更新线上服务或 TestFlight。

2026-10-14 · 增加 **EvidenceGuard / 官方 SDK 工作区切换**：iOS 顶部可进入官方 `SampleApp` 完整导航，Web 可进入资料包原版 Demo 的独立页面，保留返回按钮及分型号的检查指引。切换前停止本项目直播和取帧，返回后重新查询设备。Web 支持手动检查记录 JSON 导出。两端原版入口范围、恢复命令、原生构建要求和实机验收见 [官方 SDK 工作区](Docs/OFFICIAL-SDK-WORKSPACES.md)。切换的是界面与会话，不会替换 SDK 二进制或升级硬件固件。

2026-10-14 · 设备接入增量：加入 SN 对应的持久设备记录、iOS 官方播放器桥接、Web 直播工作台、跨客户端采集会话、新画面请求/回传与 Agent 视觉输入。默认设备列表为空，测试摄像头需显式启用。已完成本地后端与 Web 自动化检查；本轮代码的官方 SDK arm64 构建、真实账号握手、T8171 / T8214 实机取流仍待验收。这是源码更新，尚未更新部署或 TestFlight。见 [实时设备接入与联合验收](Docs/LIVE-DEVICE-INTEGRATION.md)。

下方为此前发布与验证记录，不能代替本轮变更的验收。


主分支合并前记录（本轮未重复发布）：采用“助手 / 摄像头 Skill / 任务 / 记忆 / 我的”五栏。摄像头 Skill 负责选择设备、查看画面、圈选守护和访问录像；任务独立管理状态、证据与定时概况；记忆独立管理已确认的长期 / 24 小时上下文；助手保留对话、新建话题和精简主动提醒。守护编辑分为“对象 / 条件 / 确认”，保留能力检查、试跑和占用冲突处理。“我的 → 通知与提醒”统一配置手机推送、摄像头事件、每日概况和免打扰，偏好自动保存，失败可重试。161 项 Cloud 测试、6 项移动端契约检查、模拟器编译及真实 SDK 签名归档通过。`1.0 (8)` 已完成 Apple 处理并在现有内部组显示“正在测试”；新加坡 APNs 生产发送已启用，真实手机测试已有 Apple 接受和点开回执。锁屏具体展示、build 8 真机交互与实际摄像头验收仍需分别验证。

仓库示例配置的聊天模型为 `doubao-seed-2-1-lite-260915`，Embedding 为 `doubao-embedding-vision-251215`、1024 维。图片/视频理解沿用豆包聊天模型；`EG_VIDEO_*` 仅用于同系列独立配置。官方原版 Demo 的可选 Nova Pro 代理默认关闭，不作为生产模型或回退。示例文件不含密钥，实际配置以部署为准。实际标识查看 `/api/bootstrap` 的 `agent.provider` 与 `videoModels`。仓库包括 App、Cloud、测试和 SDK 自有桥接；模型 Key、APNs 私钥、私有发布配置、运行数据和官方 SDK 二进制按现有权限单独恢复。


2026-10-14：手机、团队与 Apple 审核服务已迁至新加坡，三个环境的数据与凭证保持隔离。build 5 已通过签名归档、Apple 校验与处理，内部组显示“正在测试”；新版会自动连接新加坡并保留本地会话与草稿。美国旧实例已删除；手机需在 TestFlight 直接更新到 `1.0 (5)`，无需卸载或填写服务器配置。见 [服务器状态](Docs/SERVER-ACCESS.md) 和 [TestFlight](Docs/TESTFLIGHT.md)。

2026-10-13：`1.0 (4)` 已上传、完成 Apple 处理并加入现有内部组，组内显示“正在测试”。本轮包括独立对话、草稿恢复、摄像头事件与确定性主动提醒、合成场景及证据追问；手机 demo 云端已更新，146 项 Cloud 测试通过。手机功能与真实摄像头仍需分别验收。见 [TestFlight 记录与测试顺序](Docs/TESTFLIGHT.md)。

2026-10-12：手机内部演示包改为自动连接独立的云端服务，不再向使用者展示服务器、模型或访问令牌配置。补齐扫码识别 / 待连接设备流程，修复首页文字叠在背景树上的问题；新增明确确认的记忆、临时上下文、云端定时概况和应用内提醒箱。原生 App 已实测直接发消息并收到模型回复，保存的偏好也能进入后续对话；105 项 Cloud 测试通过。真机 `1.0 (3)` 已归档、通过 Apple 分发校验、上传并完成 Apple 处理；出口合规已保存，现有 EvidenceGuard Internal 组中的状态为“正在测试”，成员可更新。详见 [手机演示与 Personal Agent](Docs/MOBILE-DEMO-PERSONAL-AGENT.md)。以下日期为此前版本记录。

2026-10-11：`com.zhangmiao.evidenceguard` 已注册，App Store Connect 的 EvidenceGuard 记录已建立（Apple App ID `6821409514`）。首包的 ITMS-90683 权限用途说明缺失已修复；带官方 SDK 的 `1.0 (2)` 已完成签名归档、分发校验、上传和 Apple 处理。核查 SDK 的 KLIB、头文件及实际归档的加密函数后，按“标准加密算法 → 不在法国分发”保存问卷，出口合规阻塞已解除；用户确认当前仅团队和赛事测试。Beta 描述、审核操作说明、独立审核访问和联系人资料已保存，构建已提交 Beta App Review，实际状态为“正在等待审核”。测试群组尚无测试员，未创建公开邀请链接或安装到 iPhone。厂商 AnkerWebRTC 缺少 dSYM 的非阻断警告仍待主办方提供符号。见 [TestFlight 准备与 SDK 核查](Docs/TESTFLIGHT.md)。

2026-10-10：AWS Cloud 已部署，受信任 HTTPS 地址为 `https://34.218.51.85`；单团队鉴权、媒体 Range/206 与缩略图访问通过公网检查。IP 证书自动续期已配置并通过演练。iOS「服务连接」支持 Keychain 保存令牌；100 项 Cloud 测试和 iOS 编译通过。见 [Cloud 部署](Docs/CLOUD-DEPLOYMENT.md)。

2026-10-09：`EvidenceGuardSDK` 的 iPhone arm64 Debug 编译和未签名 Release 归档已通过，实际 SDK 框架及 Compose 资源已打包；普通 iOS Simulator 也通过编译。App 增加官方设备发现、事件查询与缩略图联调入口。

构建和上传成功不代表安装、设备联调或守护验收通过。摄像头及赛事 User ID / Token 到决赛才提供；外部测试等待 Apple 审核，通过后仍需邀请测试员及完成 iPhone 验收。更换 SDK 或扩大发布地区时须重新核对加密问卷。流程见 [TestFlight 准备](Docs/TESTFLIGHT.md)。

## 项目目录

| 目录 | 用途 |
| --- | --- |
| `EvidenceGuard/`、`EvidenceGuard.xcodeproj` | 原生 SwiftUI App；助手、摄像头 Skill、任务、记忆、我的五栏导航 |
| `Web/` | React / TypeScript App：助手、摄像头 Skill、任务、记忆、设置；实时取流与官方 SDK 工作区 |
| `Cloud/server/` | Agent harness、工具、录像检索、草案试跑与设备占用 |
| `Cloud/fixture-lab/` | 双路模拟摄像头与离线回归 |
| `Cloud/vision-resource-lab/` | 深度与光流资源测试、实测报告和 Git LFS 模型 |
| `SDK/Bridge/`、`SDK/prepare.py` | 官方 App SDK 的自有桥接与本机构建准备 |
| `scripts/` | SDK 恢复、iOS 归档 / 校验 / 上传 |

## 开发启动

在 Xcode 打开 `EvidenceGuard.xcodeproj`，选择 `EvidenceGuard` 与 iPhone Simulator。SDK 方案需先恢复主办方资料包：

```bash
python3 scripts/import_sdk.py /绝对路径/工具资料包.zip
python3 SDK/prepare.py --check
python3 SDK/prepare.py
```

随后打开 `EvidenceGuard.xcworkspace`，选择 `EvidenceGuardSDK`。官方 SDK 仅支持 arm64 iPhone；凭证留在手机 Keychain，官方 SDK 二进制不入 Git。环境与依赖见 [CONTRIBUTING](CONTRIBUTING.md)。

Cloud 需要 Python 3.12 与 FFmpeg：

```bash
python3 -m venv Cloud/.venv
Cloud/.venv/bin/pip install -r Cloud/server/requirements.txt
cp .env.example .env
# 按实际模型服务填写 .env；模型 Key 仅供服务端使用。
EG_ENV_FILE="$PWD/.env" Cloud/.venv/bin/uvicorn evidenceguard.app:app --app-dir Cloud/server --host 127.0.0.1 --port 8790
```

本地联调默认不启用鉴权；公网单团队测试使用 HTTPS、`EG_REQUIRE_AUTH=1` 和随机 `EG_ACCESS_TOKEN`，部署步骤见 [Cloud 部署](Docs/CLOUD-DEPLOYMENT.md)。多租户账号尚未实现。默认不托管 Web；设置 `EG_WEB_ROOT=/绝对路径/evidenceguard-ios/Web/dist` 可由 Cloud 同源托管构建产物。登录页可公开加载，API 和证据仍受团队鉴权保护。

### Web 启动

需要 Node.js 22+。在仓库根目录恢复主办方 Web SDK（只复制到被 Git 忽略的目录）：

```bash
python3 scripts/import_web_sdk.py "/绝对路径/安防赛题材料/demo工程/WebSDKDemo/public/sdk"
cd Web
npm ci
npm run dev
```

打开 `http://127.0.0.1:5173`；Vite 将 `/api` 转发到本机 8790 的 Cloud。生产构建用 `npm run build`。Windows 的后端启动命令、HTTPS/手机访问和官方参数说明见 [接入指南](Docs/LIVE-DEVICE-INTEGRATION.md)。

默认进入助手，桌面侧栏 / 手机底栏提供五个功能区。无硬件也可以先联调会话、记忆、设置、任务草案及导入录像；现场观察需要官方 SDK、真实账号与保持前台的直播。Web 当前使用应用内提醒，不包含浏览器关闭后的 Web Push。个人记录按安装标识保存，跨 iPhone / 浏览器不会自动合并；设备任务在同一团队服务内共享。详见 [Web README](Web/README.md)。

### 本轮联调顺序

1. **先配网与官方绑定。** 点击 iOS 顶部“切换官方 SDK”，在原版 Demo 的对应型号添加流程中完成配网/绑定，再返回本项目查询并同步。App 原有“扫码保存 SN”仍不是完整配网；原版流程现已接入，真实设备绑定结果仍需验收。Web 的原版 Demo 不包含手机端的完整配网导航。
2. **iOS：** 选择 `EvidenceGuardSDK` 真机方案 → 我的 → 官方 SDK → 连接账号并发现设备 → 同步设备到本项目 → 打开“实时画面与 Agent”。修改桥接后必须重新执行 `SDK/prepare.py`，不能复用旧 SampleCore 产物。
3. **Web：** 连接团队服务 → 接入设备 → 输入主办方 Web 鉴权参数 → 导入账号下的 SN → 摄像头 Skill → 开始直播。当前固定官方 PR / US 路线；不是给普通用户输入开发密钥的正式登录产品。
4. 在直播页点击“获取一张新画面”，再问“现在画面里有什么”。后端发放请求 ID，客户端取样后回传，Agent 使用对应图片或视觉核验结果回答。iOS 与 Web 使用同一 SN 时得到同一个设备 ID。
5. 停止直播、切换设备、锁屏、断网后再次提问，应返回没有有效输入，不能继续使用旧图。一个设备同一时刻只允许一个本项目采集端；其他客户端可以向同一后端请求它的当前画面。

视频通过官方链路在客户端播放，不经过本项目后端连续转码。仅请求的 JPEG/PNG 会上传给 Cloud，并按服务配置发送给视觉模型。当前依赖 iOS 页面或浏览器保持前台；后台持续守护、正式家庭成员权限、PTZ/对讲闭环和事件录像导入不属于本轮已完成功能。

### 检查

```bash
python -m pytest Cloud/server/tests -q
cd Web
npm test
npm run build
npx playwright install chromium firefox webkit
npm run test:browser
```

GitHub Checks 已加入 Web 检查，并保留 Cloud 与普通 iOS Simulator 构建。官方 SDK 不上传仓库，带 SDK 的 arm64 构建由持有资料包的 Mac 完成。详细检查范围和失败处理见 [实时接入指南](Docs/LIVE-DEVICE-INTEGRATION.md)。

## 既有功能与验证记录

下方记录原生 App / harness 的功能演进；模拟、公开视频回放与真实摄像头验证相互独立。

## 对话与圈选编辑 v1.0

AI 对话固定显示草案入口，摄像头图片可直接进入独立圈选页。保存后返回原对话，当前任务状态来自数据库。详见 [交互修复与验证](CHAT-EDITOR-v1.0.md)。

## 按秒检测与验收准备 v0.9

检测间隔最低 3 s，确认跨度与检测间隔分别配置；录像试跑使用采样图片，旧按帧报告不再用于启用。真机发布仍需完成 SDK 联调与现场验收。详见 [时间规则与验收边界](SKILL-TIMING-v0.9.md)。下方 v0.8 及更早内容仅为历史记录。

## Skill 合同与启用前试跑 v0.8

创建前检查能力，草案明确任务类型、可观察条件与时间要求。包裹回放先在隔离环境试跑，App 展示逐段结果和片段；核验当前版本报告后才可继续启用，不支持的任务不能冒充包裹规则。一次真实试跑7次观察、36.25秒，未影响原守护或产生正式告警。详见 [v0.8 实现与验证](Docs/SKILL-CONTRACT-v0.8.md)。

## 录像回放守护 v0.7

已接通助手草案、回放源选择、区域编辑、设备占用确认、逐段视频模型观察与可播放的提醒证据。公开拿取样例在到达第 8 秒时形成提醒，定位原片约第 5 秒；该轮模型处理约 35 秒，属于回放功能验证。模型尾点舍入误拒绝已修复，HTTP 限流仍明确作为失败。详见 [v0.7 实测与 SDK 边界](Docs/REPLAY-GUARD-v0.7.md)。

## 历史录像验收 v0.6

新增手动时间范围、实际复核进度、基于本轮回执的回答，以及从定位前 3 秒播放。公开样片 12 次重复测试中 9 次通过结构化检查、3 次没有有效结果；仍不据此批准自动守护。详见 [v0.6 实现与评测](Docs/VIDEO-RELIABILITY-v0.6.md)。

## 历史录像闭环 v0.5

已接入实际视频 Embedding、Lite 视频复核、原生可播放证据卡及录像库。使用路径：AI → 历史回顾 → 查录像 → 发送 → 播放原片。实测定位公开样片中的包裹拿取动作至约第 5 秒，但 Lite 在重复测试中出现内容幻觉，尚不通过自动守护可靠性验收。细节与尚未验证的边界见 [v0.5 验收](Docs/VIDEO-HISTORY-v0.5.md)。

## Skill 与摄像头联动

已接入任务上下文、助手新图工具、双路截图回执、状态转换引擎、持久化图片和运行记录。v0.4 增加每台摄像头的实时任务独占、用户确认切换、只读历史分析及两款摄像头 SDK Bridge。详见 [v0.4 实现与验收](Docs/CAMERA-OWNERSHIP-v0.4.md)；原有状态引擎见 [v0.3](Docs/SKILL-RUNTIME-v0.3.md)。

## 本次基础交互调整

- 五个标签独立维护导航栈，助手为默认页；详情页隐藏标签栏，原生返回恢复根页面。“我的”集中管理资料、偏好、服务与联调。
- 主对话持续接收提醒，可通过左上角对话列表切换话题、右上角新建对话。新话题不停止已有守护。
- 输入框上方只保留一个范围入口，将现场 / 历史与摄像头放进弹层；历史时间条件仍明确显示。两个范围的记录、草稿和工具权限保持隔离。
- 助手专注对话；提醒卡保留来源类别与限制，完整正文和依据展开查看，证据可直接打开。任务状态放在独立任务页。
- 摄像头 Skill 提供设备切换、画面、圈选守护和录像库入口；不会把任务列表重复放在此页。
- 任务按运行中、待确认、已暂停、已结束组织；定时分区读取实际每日概况设置，不伪造预约启停功能。
- 记忆页支持全部 / 长期 / 24 小时筛选、显式添加与确认移除。空白不可保存，未保存输入关闭前确认，保存失败保留内容。
- 守护设置分为对象、条件、确认三步，圈选使用独立画面编辑器；保存不启用，缺失能力或必要试跑时不能开始。
- 提示语只填入输入框；用户编辑后点击发送。语音先转写到输入框，取消或空录音不会发送。发送失败保留请求 ID，重试避免重复。
- 五栏界面改版之外，现已接入原生 APNs 授权、设备登记和持久化投递队列；新加坡手机服务生产发送已启用，仍待真机验收。详见 [手机通知接入](Docs/APNS.md)。摄像头执行能力与用户确认边界保持不变。

## 运行

开发构建在 Xcode 打开 `EvidenceGuard.xcodeproj`，选择 iPhone Simulator，默认连接 `http://127.0.0.1:8790`。内部演示发布必须使用私有 demo xcconfig，打开即连接云端，手机没有配置表单；见 [构建说明](Docs/MOBILE-DEMO-PERSONAL-AGENT.md)。

服务未连接时显示连接状态和空状态，不伪造运行任务、证据或 AI 回复。

双路模拟摄像头（需要 Python、npm、FFmpeg）：

```bash
cd Cloud/fixture-lab
python3 scripts/setup.py
.venv/bin/python scripts/run.py
```

服务端（视频导入需 PATH 中可用的 FFmpeg/ffprobe）：

当前按单个服务进程运行；不要增加 `--workers` 或部署多个副本。设备命令锁尚未迁移到分布式协调服务。

```bash
cd Cloud
python3 -m venv .venv
.venv/bin/pip install -r server/requirements.txt
EG_ENV_FILE=/绝对路径/evidenceguard.env .venv/bin/uvicorn evidenceguard.app:app --app-dir server --host 127.0.0.1 --port 8790
```

私有环境文件放在工程外，不放进 App 或版本库：

```dotenv
EG_MODEL_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
EG_MODEL_ID=doubao-seed-2-1-lite-260915
EG_MODEL_API_KEY=填写自己的密钥
EG_MODEL_VISION=1
EG_EMBED_MODEL_ID=doubao-embedding-vision-251215
```

`EG_MODEL_VISION=1` 时，摄像头新图和已保存图片可直接交给主助手模型。主助手为纯文本时设为 `0`，并配置独立的 `EG_VIDEO_BASE_URL / EG_VIDEO_MODEL_ID / EG_VIDEO_API_KEY`；当前自动视觉回退用于实时截图，历史 `read_stored_image` 尚无同样的回退。省略某个 `EG_VIDEO_*` 变量才会继承对应 `EG_MODEL_*`，显式空值不会继承。Embedding 可用 `EG_EMBED_BASE_URL / EG_EMBED_API_KEY` 独立配置；更换模型、instructions 或采样策略后须重建索引，不能仅凭相同的 1024 维数混用旧向量。

系统提示词和视觉输出 Schema 在服务端源码中维护，目前没有独立提示词管理或图片生成 API。语音输入转为用户确认后的文字，不向本项目 Agent 上传录音。密钥只供服务端使用。真机访问需配置手机可达的受信任 HTTPS 地址及签名，不要求手机与云端在同一局域网；本地开发默认服务仅监听本机。

## 已检查与边界

此前版本通过 Xcode iOS Simulator 编译，并在 iPhone 17 Pro 模拟器检查了五个标签、AI 输入与发送、输入草稿保留、键盘避让、语音弹层取消、摄像头详情及多级返回。此前已验证模型调用；Embeddings 的联调选型与验证范围见 v0.5 文档。新增实时设备链路以本文顶部的本轮状态为准，麦克风完整转写仍需真机验收。

双路 RTSP 合成场景仅在 `EG_CAMERA_MODE=fixture` 时启用；默认使用空设备清单及客户端导入的真实设备记录。T8171 / T8214 已有官方媒体接入代码，本轮实机验收仍待完成。已有单团队鉴权及 APNs 接入；正式多租户、通用视觉守护和持续后台采集仍需后续开发与验收。推送状态见 `Docs/APNS.md`，设备接口见 `Cloud/CAMERA-SDK-CONTRACT.md` 与本轮接入指南。

Dashboard 展示更新：图片分析可查看事件原图及新豆包调用的实际上传图片；视频向量库可播放入库录像，查看真实查询、候选相似度、复核结论和定位片段。长 ID 收入详情。作品预览复用原生 iOS 素材与五栏结构，仍明确标注为网页演示。媒体公开范围、采集上限及部署步骤见 [比赛网站文档](Docs/COMPETITION-WEBSITE.md)。
