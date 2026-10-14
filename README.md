# EvidenceGuard · iOS / Web / Cloud

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

仓库示例配置的聊天模型为 `doubao-seed-2-1-lite-260915`，Embedding 为 `doubao-embedding-vision-251215`、1024 维。图片/视频理解可独立配置，官方 Demo 另用固定 `hackathon/v_model/nova-pro` 网关；示例名称不能代替部署配置。实际标识查看 `/api/bootstrap` 的 `agent.provider` 与 `videoModels`。仓库包括 App、Cloud、测试和 SDK 自有桥接；模型 Key、APNs 私钥、私有发布配置、运行数据和官方 SDK 二进制按现有权限单独恢复。


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
