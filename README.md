# EvidenceGuard · iOS / Web / Cloud

本仓库维护原生 iOS App、响应式 Web 设备工作台和共用的 Cloud Agent。设备、实时取帧、观察回执和媒体统一经过同一套 API；两端分别使用主办方原生 SDK 与 Web SDK 播放视频。当前接入功能在 `dongrunze` 分支开发。

- [iOS 主仓库](https://github.com/zhangmiao03/evidenceguard-ios)
- [此前独立 Web 原型](https://github.com/zhangmiao03/evidenceguard-web)：历史参考；本轮 Web 实现在本仓库 `Web/`。
- [此前合并仓库](https://github.com/zhangmiao03/evidenceguard-hackathon)：保留原来的历史参考。
- [服务器访问与团队协作](Docs/SERVER-ACCESS.md)：已验证的 SSM 会话入口、团队授权、SSH 备用连接、新加坡三个后端环境与迁移状态。
- [深度与光流实测、复现工具和模型](Docs/VISION-RESOURCE-BENCHMARK.md)：本机 CPU/内存限额实验，三份 ONNX 权重通过 Git LFS 获取。

## 当前进度

2026-10-14 · 增加 **EvidenceGuard / 官方 SDK 工作区切换**：iOS 顶部可进入官方 `SampleApp` 完整导航，Web 可进入资料包原版 Demo 的独立页面，保留返回按钮及分型号的检查指引。切换前停止本项目直播和取帧，返回后重新查询设备。Web 支持手动检查记录 JSON 导出。两端原版入口范围、恢复命令、原生构建要求和实机验收见 [官方 SDK 工作区](Docs/OFFICIAL-SDK-WORKSPACES.md)。切换的是界面与会话，不会替换 SDK 二进制或升级硬件固件。

2026-10-14 · 设备接入增量：加入 SN 对应的持久设备记录、iOS 官方播放器桥接、Web 直播工作台、跨客户端采集会话、新画面请求/回传与 Agent 视觉输入。默认设备列表为空，测试摄像头需显式启用。已完成本地后端与 Web 自动化检查；本轮代码的官方 SDK arm64 构建、真实账号握手、T8171 / T8214 实机取流仍待验收。这是源码更新，尚未更新部署或 TestFlight。见 [实时设备接入与联合验收](Docs/LIVE-DEVICE-INTEGRATION.md)。

下方为此前发布与验证记录，不能代替本轮变更的验收。

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
| `EvidenceGuard/`、`EvidenceGuard.xcodeproj` | 原生 SwiftUI App；首页保留设计，其余页使用紧凑标题与返回 |
| `Web/` | React / TypeScript 设备工作台：账号接入、设备选择、官方直播、Agent 观察与证据 |
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

### 本轮联调顺序

1. **先配网与官方绑定。** 点击 iOS 顶部“切换官方 SDK”，在原版 Demo 的对应型号添加流程中完成配网/绑定，再返回本项目查询并同步。App 原有“扫码保存 SN”仍不是完整配网；原版流程现已接入，真实设备绑定结果仍需验收。Web 的原版 Demo 不包含手机端的完整配网导航。
2. **iOS：** 选择 `EvidenceGuardSDK` 真机方案 → 我的 → 官方 SDK → 连接账号并发现设备 → 同步设备到本项目 → 打开“实时画面与 Agent”。修改桥接后必须重新执行 `SDK/prepare.py`，不能复用旧 SampleCore 产物。
3. **Web：** 进入工作台 → 接入设备 → 输入主办方 Web 鉴权参数 → 导入账号下的 SN → 开始直播。当前固定官方 PR / US 路线；不是给普通用户输入开发密钥的正式登录产品。
4. 在直播页点击“获取一张新画面”，再问“现在画面里有什么”。后端发放请求 ID，客户端取样后回传，Agent 使用对应图片或视觉核验结果回答。iOS 与 Web 使用同一 SN 时得到同一个设备 ID。
5. 停止直播、切换设备、锁屏、断网后再次提问，应返回没有有效输入，不能继续使用旧图。一个设备同一时刻只允许一个本项目采集端；其他客户端可以向同一后端请求它的当前画面。

视频通过官方链路在客户端播放，不经过本项目后端连续转码。仅请求的 JPEG/PNG 会上传给 Cloud，并按服务配置发送给视觉模型。当前依赖 iOS 页面或浏览器保持前台；后台持续守护、正式家庭成员权限、PTZ/对讲闭环和事件录像导入不属于本轮已完成功能。

### 检查

```bash
python -m pytest Cloud/server/tests -q
cd Web
npm test
npm run build
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

- 品牌头图仅出现在首页。Skill、AI、证据、我的使用紧凑的原生标题栏。
- 五个标签独立维护导航栈；详情页有原生返回，详情隐藏标签栏，返回根页面后恢复。
- AI 标签直接进入对话。底部始终提供多行文字输入、语音、发送及摄像头选择；键盘弹出时输入框随之上移。
- 摄像头预览通过右上角按钮展开，不占用默认聊天空间。
- 提示语只填入输入框；用户编辑后点击发送。语音先转写到输入框，取消或空录音不会发送。
- 同次 App 运行中，切换标签或返回会保留未发送草稿。发送中显示进度，可以停止；失败显示错误和编辑重试。
- Skill 草案需要检查并确认，不能因返回或普通对话而自动启用。

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

`EG_MODEL_VISION=1` 表示助手调用摄像头工具成功后，可将新画面交给模型；不发送录音。密钥只供服务端使用。真机访问需配置同一网络内可访问的服务地址及签名；当前默认服务仅监听本机。

## 已检查与边界

此前版本通过 Xcode iOS Simulator 编译，并在 iPhone 17 Pro 模拟器检查了五个标签、AI 输入与发送、输入草稿保留、键盘避让、语音弹层取消、摄像头详情及多级返回。此前已验证模型调用；Embeddings 的联调选型与验证范围见 v0.5 文档。新增实时设备链路以本文顶部的本轮状态为准，麦克风完整转写仍需真机验收。

双路 RTSP 合成场景仅在 `EG_CAMERA_MODE=fixture` 时启用；默认使用空设备清单及客户端导入的真实设备记录。T8171 / T8214 新增官方媒体接入代码，尚未做本轮实机验收。已有单团队鉴权与历史部署记录；正式多租户、通用持续视觉守护和后台推送仍需后续开发。接口边界见 `Cloud/CAMERA-SDK-CONTRACT.md` 与本轮接入指南。
