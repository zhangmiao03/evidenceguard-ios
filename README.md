# EvidenceGuard · Web / iOS / Cloud

团队共用仓库：Web 与原生 SwiftUI App 使用同一套 Cloud API、harness、Skill 校验和录像索引。`Cloud/fixture-lab` 继续作为模拟摄像头工具。iOS 保留原生产品交互；Web 是新增客户端。

## 当前开发入口

| 目录 | 用途 |
| --- | --- |
| `Web/` | 首页、AI 对话、圈选编辑、试跑确认、录像证据、官方 Web SDK 联调 |
| `EvidenceGuard/`、`EvidenceGuard.xcodeproj` | 原生 iOS；Simulator 和 SDK 真机方案分别构建 |
| `Cloud/server/` | 共用 Agent harness、工具、任务/设备占用、录像检索 |
| `SDK/Bridge/`、`SDK/prepare.py` | 自有 SDK 桥接与本地构建准备 |
| `scripts/` | 恢复官方 SDK、准备 iOS 归档 |

先安装 Python 3.12、Node 22.12+ 和 FFmpeg，在仓库根目录运行：

```bash
python3 -m venv Cloud/.venv
Cloud/.venv/bin/pip install -r Cloud/server/requirements.txt
cp .env.example .env
# 按实际模型服务填写 .env；模型 Key 不交给浏览器。
EG_ENV_FILE="$PWD/.env" Cloud/.venv/bin/uvicorn evidenceguard.app:app --app-dir Cloud/server --host 127.0.0.1 --port 8790
```

另开终端启动 Web：

```bash
npm --prefix Web ci
npm --prefix Web run dev
# 打开 http://127.0.0.1:5173
```

Web 开发服务器把 `/api` 代理到 8790。`npm --prefix Web run build` 后，重启 Cloud 可在 8790 同源托管 `Web/dist`。当前服务用于本地单团队联调，公网部署还需 HTTPS、身份与媒体权限。

摄像头模拟器的启动方式见下方。真实摄像头需要赛事凭证和官方资料包，先恢复本地 SDK：

```bash
python3 scripts/import_sdk.py /绝对路径/工具资料包.zip --web-only
```

官方 SDK、密钥、数据库、录像和本地验收截图不入 Git。Web SDK 当前支持联调预览及 ≥3 s 抽帧，尚未进入正式守护 Worker；App SDK 新增设备发现桥接，实际 SDK 真机编译与现场验证仍待完成。

团队分工、分支和检查见 [CONTRIBUTING](CONTRIBUTING.md)；双端边界见 [架构说明](Docs/WEB-APP-ARCHITECTURE.md)；iOS 外部分发见 [TestFlight 准备](Docs/TESTFLIGHT.md)。

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

在 Xcode 打开 `EvidenceGuard.xcodeproj`，选择 iPhone Simulator，点击 Run。默认服务地址是 `http://127.0.0.1:8790`，可在“我的 → 服务连接”修改，无须修改源码。

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

本次通过 Xcode iOS Simulator 编译，并在 iPhone 17 Pro 模拟器检查了五个标签、AI 输入与发送、输入草稿保留、键盘避让、语音弹层取消、摄像头详情及多级返回。当前已切换到方舟 Lite，并验证真实视频模型调用；Embeddings 的联调选型与验证范围见 v0.5 文档。麦克风完整转写仍需在真机实际说话验收。

当前摄像头执行器使用双路 RTSP 合成场景与测试标记；T8171 / T8214 正式 SDK 入口保留，尚未做实机接入验收。通用视觉守护、后台推送、正式公网部署与鉴权也尚未完成。接口边界见 `Cloud/CAMERA-SDK-CONTRACT.md`。
