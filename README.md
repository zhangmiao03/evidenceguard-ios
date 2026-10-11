# EvidenceGuard · iOS / Cloud

当前主要开发原生 iOS App；Cloud Agent、miimiao 参考的 harness、Skill 校验和录像索引由此仓库维护。Web 原型已拆到独立仓库，暂缓开发，不影响 iOS 编译。

- [iOS 主仓库](https://github.com/zhangmiao03/evidenceguard-ios)
- [Web 原型仓库](https://github.com/zhangmiao03/evidenceguard-web)
- [此前合并仓库](https://github.com/zhangmiao03/evidenceguard-hackathon)：保留原来的历史参考。

## 当前进度

2026-10-12：手机内部演示包改为自动连接独立的云端服务，不再向使用者展示服务器、模型或访问令牌配置。补齐扫码识别 / 待连接设备流程，修复首页文字叠在背景树上的问题；新增明确确认的记忆、临时上下文、云端定时概况和应用内提醒箱。原生 App 已实测直接发消息并收到模型回复，保存的偏好也能进入后续对话；105 项 Cloud 测试通过。真机 `1.0 (3)` 已归档、通过 Apple 分发校验、上传并完成 Apple 处理；出口合规已保存，现有 EvidenceGuard Internal 组中的状态为“正在测试”，成员可更新。详见 [手机演示与 Personal Agent](Docs/MOBILE-DEMO-PERSONAL-AGENT.md)。以下日期为此前版本记录。

2026-10-11：`com.zhangmiao.evidenceguard` 已注册，App Store Connect 的 EvidenceGuard 记录已建立（Apple App ID `6821409514`）。首包的 ITMS-90683 权限用途说明缺失已修复；带官方 SDK 的 `1.0 (2)` 已完成签名归档、分发校验、上传和 Apple 处理。核查 SDK 的 KLIB、头文件及实际归档的加密函数后，按“标准加密算法 → 不在法国分发”保存问卷，出口合规阻塞已解除；用户确认当前仅团队和赛事测试。Beta 描述、审核操作说明、独立审核访问和联系人资料已保存，构建已提交 Beta App Review，实际状态为“正在等待审核”。测试群组尚无测试员，未创建公开邀请链接或安装到 iPhone。厂商 AnkerWebRTC 缺少 dSYM 的非阻断警告仍待主办方提供符号。见 [TestFlight 准备与 SDK 核查](Docs/TESTFLIGHT.md)。

2026-10-10：AWS Cloud 已部署，受信任 HTTPS 地址为 `https://34.218.51.85`；单团队鉴权、媒体 Range/206 与缩略图访问通过公网检查。IP 证书自动续期已配置并通过演练。iOS「服务连接」支持 Keychain 保存令牌；100 项 Cloud 测试和 iOS 编译通过。见 [Cloud 部署](Docs/CLOUD-DEPLOYMENT.md)。

2026-10-09：`EvidenceGuardSDK` 的 iPhone arm64 Debug 编译和未签名 Release 归档已通过，实际 SDK 框架及 Compose 资源已打包；普通 iOS Simulator 也通过编译。App 增加官方设备发现、事件查询与缩略图联调入口。

构建和上传成功不代表安装、设备联调或守护验收通过。摄像头及赛事 User ID / Token 到决赛才提供；外部测试等待 Apple 审核，通过后仍需邀请测试员及完成 iPhone 验收。更换 SDK 或扩大发布地区时须重新核对加密问卷。流程见 [TestFlight 准备](Docs/TESTFLIGHT.md)。

## 项目目录

| 目录 | 用途 |
| --- | --- |
| `EvidenceGuard/`、`EvidenceGuard.xcodeproj` | 原生 SwiftUI App；首页保留设计，其余页使用紧凑标题与返回 |
| `Cloud/server/` | Agent harness、工具、录像检索、草案试跑与设备占用 |
| `Cloud/fixture-lab/` | 双路模拟摄像头与离线回归 |
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

本地联调默认不启用鉴权；公网单团队测试必须使用 HTTPS、`EG_REQUIRE_AUTH=1` 和随机 `EG_ACCESS_TOKEN`，部署步骤见 [Cloud 部署](Docs/CLOUD-DEPLOYMENT.md)。多租户账号尚未实现。默认不托管 Web；若日后需要同源部署独立 Web 构建，可显式设置 `EG_WEB_ROOT=/绝对路径/EvidenceGuard-Web/dist`。仓库分工见 [协作边界](Docs/WEB-APP-ARCHITECTURE.md)。

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

本次通过 Xcode iOS Simulator 编译，并在 iPhone 17 Pro 模拟器检查了五个标签、AI 输入与发送、输入草稿保留、键盘避让、语音弹层取消、摄像头详情及多级返回。当前已切换到方舟 Lite，并验证真实视频模型调用；Embeddings 的联调选型与验证范围见 v0.5 文档。麦克风完整转写仍需在真机实际说话验收。

当前摄像头执行器使用双路 RTSP 合成场景与测试标记；T8171 / T8214 正式 SDK 入口保留，尚未做实机接入验收。通用视觉守护、后台推送、正式公网部署与鉴权也尚未完成。接口边界见 `Cloud/CAMERA-SDK-CONTRACT.md`。
