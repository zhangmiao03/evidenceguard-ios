# demo 工具链部署、云端差异与联调记录

首次部署：2026-10-15；中断后复核：2026-10-16。分支：`dongrunze`；现有 PR：[#5](https://github.com/zhangmiao03/evidenceguard-ios/pull/5)。首次比较基准为仓库 `7d9d360`，它已经包含 `main@cc16c98`。10 月 16 日重新 fetch 后，main 仍没有新增未合入提交，另一个功能分支已更新。

## 1. 比较范围与结论

直接通过项目 EC2 的 SSM 读取部署文件，按路径和 SHA-256 对照 Git 工作树；对不同的源码逐文件读取，并以 `cc16c98` 做三方合并。没有以运行日志或部署说明代替源码。仅下载 Python、requirements 和工具 contract JSON，没有下载环境文件、模型密钥、数据库或用户图片。

| 部署环境 | 实际原始源码目录 | 与 `7d9d360` 一致 | 内容不同 | 仅云端有 | 仅仓库有 | 本次处理 |
|---|---|---:|---:|---:|---:|---|
| demo | `/opt/evidenceguard-demo/Cloud/server` | 53 | 18 | 7 | 8 | 保留云端修复，补齐仓库工具链，发布独立目录 |
| team | `/opt/evidenceguard/Cloud/server` | 16 | 16 | 1 | 47 | 只比较，保持运行版本 |
| review | 与 team 共用源码、独立数据库 | 同 team | 同 team | 同 team | 同 team | 不重新部署或重启 |

计数范围为应用/测试 `.py`、contract `.json` 与 `requirements.txt`，不是仅运行时模块数。完整路径、部署前哈希、仓库基准哈希、合并后哈希和处置在 [逐文件差异 CSV](CLOUD-REPOSITORY-COMPARISON-2026-10-15.csv)。正式发布另用包内 `manifest.json` 检查静态 Web、测试素材和所有运行文件。

### demo 上保留并纳入 Git 的改动

| 文件 | 云端已有行为 | 合并结果 |
|---|---|---|
| `assistant_identity.py`、`conversations.py`、`push.py` | anker 身份/自然表达、主对话显示名和中性通知文本 | 保留原 ID、通知 scope 和安装端隔离 |
| `memory.py`、`personal.py` | 聊天完成后自动提取明确自述、持久作业、临时有效期、删除抑制、100 条上限 | 保留；不把视觉/邮件推断存成用户事实；补齐两端可选开关、来源和重试 |
| `connectors.py`、`access.py` | Gmail/飞书只读 OAuth、PKCE、加密令牌、私有安装 proof、用户主动提供的手机快照 | 保留；新增路由不绕过既有团队鉴权；OAuth 回调仅按固定 provider 放行 |
| `camera/watch.py` | 用户按设备开启的定时取样；最短 300 秒、预算/新鲜度/重复通知约束 | 复用同一 CameraService；控制在途或 unknown 时不生成观察结果 |
| `camera/ingest.py`、`proactive.py` | 新鲜 human/ring 事件缺图时允许元数据提醒，明确没有视觉证据 | 保留；Web 增加 `metadata_only` 文案，不能显示“核验完成” |
| `harness/providers.py` | 无工具的记忆请求不发送空 `tools/tool_choice` | 保留，兼容真实 OpenAI 格式模型服务 |
| `app.py` | memory/watch worker、connector 路由、用户身份检查和退出清理 | 与仓库 HardwareGateway、live routes、hardware routes 并存 |
| `harness/runtime.py` | 记忆调度、个人 context、connector 只读工具和身份提示词 | 同时保留 `clientPlatform`、本轮硬件 allowlist、确认回执、取消和 unknown 规则 |
| `requirements.txt` | `cryptography==50.0.2` | 加入依赖；demo 现有虚拟环境已安装该版本，无在线升级 |

云端新增三份测试：`test_camera_watch.py`、`test_connectors.py`、`test_memory_extraction.py`；同时保留云端已有对话、个人记忆、提示词和推送测试改动。

`app.py` 与 `harness/runtime.py` 的冲突按功能合并：请求端平台与私有安装身份都传入；为每轮生成已授权硬件工具集合，再按安装授权附加只读 connector 工具，不修改共享工具表。原有硬件生命周期与停止分支保留。

### 仓库中保留并补到 demo 的改动

- `hardware_tools/` 的 5 个 Python 模块与 2 份 contract JSON；`test_hardware_tools.py`。
- `camera/live.py`、`camera/service.py`：实时 challenge、视角版本、动作占用及未知结果门禁。
- `harness/tools.py`：仅向当前任务开放已验证工具；历史查询不获得硬件动作。
- `test_live_devices.py`：旧帧、失效会话、错误来源以及并发采集回归。
- Web 五栏产品、事件时间线、硬件操作卡、前台采集，以及原版官方 Demo/浏览器 SDK 静态资源。原 demo 没有设置 `EG_WEB_ROOT`，本轮补上同源 Web 托管。

### team/review 不是另一套待覆盖的新修复

16 个变化文件均找到完全一致的 Git 历史版本：主要来自 `3ab237df`；`app.py/access.py` 来自 `3902afcc`；`harness/providers.py` 来自 `58054db1`。这比凭功能名称推断版本更可靠。云端额外的 `migration_stage.py` 只创建 `start_worker=False` 的暂存入口，不并入正式应用。完整 commit SHA 已列入 CSV。

## 2. 三端如何联调

| 链路 | 当前接入 | 验收边界 |
|---|---|---|
| iOS → Cloud | 同一团队 token、安装 ID、`clientPlatform=ios`；官方设备身份同步，前台 live session 与工具执行器 | Windows 上验证 HTTP 契约和共享 Kotlin；SwiftUI/Xcode/arm64 SDK 仍需 Mac |
| Web → Cloud | 同源 `/api/*`、独立浏览器安装 ID、`clientPlatform=web`；事件列表、工具确认/回执、官方版本切换 | 浏览器协议/界面测试与真实云端契约分别记录，不能用测试替身声称真机成功 |
| Cloud → iOS 执行器 | `/api/hardware/executors/{id}/claim` 领取；原生 SDK 有限动作；`result` 回传 | iOS 必须前台在线；无 executor、无版本验证时不向 Agent 放开动作 |
| Web 取流 → Agent | 官方 SDK 解码 → Cloud challenge → 新帧上传 → `/api/media/*` → 已配置视觉模型 | 需要有效官方账号及真实设备；SDK 事件缩略图不能替代直播帧 |
| iOS 取流 → Agent | 原生播放器新帧 → 同一 challenge/证据库 → Agent | 与 Web 使用同一来源/时间/权限约束 |
| 定时观察 → 工具门禁 | cloud watch 调用 CameraService，不绕过硬件锁和视角检查 | 观察配置默认关闭；控制 unknown 时不取图、不提醒 |

工具 12 项 API、字段、型号限制和人工诊断步骤见 [硬件工具接入说明](HARDWARE-TOOLS-INTEGRATION.md)。T8171 和 T8214 不共享所有工具；Web 本地执行器仅登记观察路线，其他已接入控制委派给在线 iOS。SDK acknowledged 不是物理效果验证，29 个定义不是 29 个可执行功能。对讲、SD 下载、门铃快捷回复播放及通用真机持续 Skill 仍未完成。

云端原有新增 API 同时保留：

| 方法 / 路径 | 用途 / 客户端兼容 |
|---|---|
| `GET/PUT /api/camera-observation[/{camera_id}]` | 按设备查询/配置定时观察；本轮未新增 App/Web 定时观察编辑 UI |
| `PUT /api/personal/memory-options?enabled=...` | 开关自动整理；两端只在响应包含 `automaticMemory` 时显示入口 |
| `POST /api/personal/memory-retry` | 人工重试失败的记忆作业 |
| `GET /api/connectors` | 已授权只读服务状态；要求 `X-EG-Private-Key` |
| `POST /api/connectors/{provider}/authorize` | OAuth 开始，provider 为 gmail/feishu |
| `GET /api/connectors/oauth/callback/{provider}` | OAuth 返回；以 state/PKCE/安装授权校验，不是通用公开 API |
| `POST /api/connectors/{provider}/complete` | 完成授权 |
| `DELETE /api/connectors/{provider}` | 断开连接 |
| `POST/GET/DELETE /api/phone-context` | 用户主动共享的日历/提醒快照；不直接读手机 |

connector UI 和手机数据授权 UI 尚不在本轮 iOS/Web 中；保留的是云端已有接口。已经绑定私有 proof 的安装必须继续携带原 proof，不能退回仅凭安装 ID 读取个人数据；旧版未绑定安装仍兼容。两端个人记忆按安装隔离，团队设备/任务共享，不能把同一团队 token 当作个人记忆跨端同步。

## 3. 发布与回滚机制

本次使用 `Cloud/demo_release/` 脚本，固定作用于 demo。归档白名单只含源代码、合成测试素材、Web 构建文件与 manifest；官方 SDK 构建留在部署包，不加入 Git。

1. `package.py` 生成完整文件哈希和基准 commit，拒绝异常资源类型。
2. `upload.py` 经 SSM 分块校验后原子生成新的 release 目录；增量上传也会重新验证复用文件全部哈希，不修改旧目录。
3. `preflight.py` 清空继承的 EG 配置，不读取生产凭据；跑 Linux 后端测试，对生产数据库做只读 SQLite backup，再在临时副本上运行迁移、比较关键业务表行数和 `quick_check`。
4. `activate.py` 再次校验云端源码没有漂移，检查没有运行中 Agent；通过现有 observer 的兼容性测试后，停止 demo、备份 SQLite、增加 `50-demo-tools.conf`，只替换 demo 的代码路径与 `EG_WEB_ROOT`。
5. 保留 `/etc/evidenceguard-demo/cloud.env`、原 venv、端口 8792、团队 token、模型/APNs 配置、数据目录、原源码、nginx 和监控入口。collector 仅更新 demo 源码位置，team/review 的 PID 必须不变。
6. 新进程健康/鉴权/官方静态入口失败则恢复旧代码配置。通常回滚不恢复数据库，避免丢掉切换后产生的业务记录。数据库备份是灾难恢复材料，需单独评估数据损失后处理。

发布命令（仓库根目录，已有 AWS SSM 身份）：

```powershell
# 按项目原流程恢复官方 SDK，再构建：cd Web; npm run build:official; npm run build
python Cloud/demo_release/package.py --baseline PATH_TO_AUDIT_INVENTORY --output PATH_TO_RELEASE_TGZ
python Cloud/demo_release/upload.py PATH_TO_RELEASE_TGZ
# 将输出 release 路径写入维护脚本，再用 scripts/cloud_command.py --file 执行。
```

服务器上执行：

```sh
/opt/evidenceguard-demo/venv-build10/bin/python RELEASE/activate.py --release RELEASE
# 常规回滚；BACKUP 是该次 activation 输出的私有备份目录。
/opt/evidenceguard-demo/venv-build10/bin/python RELEASE/activate.py --rollback BACKUP
```

SSM 结果不确定时，使用 `scripts/cloud_command.py --resume COMMAND_ID` 读取同一次命令，不重复部署。回滚若检测到后续操作人改过 drop-in 或 demo 的 collector source，会停下供重新比对，不能无条件覆盖后续改动。

## 4. 测试证据与局限

本轮新增回归验证：新旧 iOS/Web 请求、安装 proof、关闭记忆后不排队、connector 包装不扩大硬件权限、历史模式禁止动作、watch 遵守 unknown 控制锁；发布脚本另有代码回滚保留新数据、环境隔离、源码漂移与后续改动拦截测试。

首轮 Linux 预检发现打包时漏了三张仓库自带的合成测试素材，6 项测试因此失败；已补齐白名单素材。该次只在临时库测试，没有切换原服务。Web 新增开关测试已修正为等待异步保存回执，四浏览器专项通过。

最终部署、哈希、备份路径、Linux 测试及真实模型回执见本节下方的发布验收记录。当前没有登记真实摄像头或门铃，不能把接口/替身测试写成硬件验收；仍需 Mac + 官方 SDK + T8171/T8214 按型号验证取流、云台、灯光、隐私、网络中断及后台恢复。

### 10 月 15 日实际发布验收

- 发布时间：2026-10-15 09:32（新加坡时间）。SSM activation `detailed result` 保存在本机私有分析目录；命令返回 Success。
- 发布目录：`/opt/evidenceguard-demo/releases/tools-6336a97c95c4bc5a`；114 个文件；archive SHA-256 `6336a97c95c4bc5adffa08deff9fa55f073d387fd1272de85152940a286b25d6`；内容 manifest 摘要 `20df34f063e45216ca3fc555d1a929b940fe53836628636daaf36ef1fbd47aef`。
- 私有备份：`/var/backups/evidenceguard-demo-tools/20261015T013208054377Z`。原库副本 quick_check 为 ok；迁移前后 skills 4、media/evidence 各 15、runs 29、recordings 1、personal_profiles 2、personal_memories 1、push_devices 1，行数一致。备份不进入 Git。
- Linux 后端全量 **263 passed**；监控桥接验证 model→tool→model、鉴权、工具参数和无重复埋点均通过。team/review 的 PID 未变化。
- iOS 请求契约 run：`demo-toolchain-ios-865c70d0de584f6cbfa68eb05df1dddf`；Web 契约 run：`demo-toolchain-web-ea5459c408fd411db66a1548d4d31f51`。两者均 completed，各 2 次 `doubao-seed-2-1-lite-260915` 请求、HTTP 200，均调用 `list_camera_capabilities` 与 `list_tasks`。测试安装关闭自动记忆，不执行摄像头动作或推送。
- 10 月 16 日公网再次读取监控，以上两个 trace 仍可核实；Web 首页和 SDK 原版入口 200；匿名 bootstrap、hardware snapshot、sdk events 均 401。页面主资源与 10 月 15 日发布构建 SHA-256 一致。

这些真实模型结果属于初次部署版本，不能直接当作随后 Codex 执行器的新验收。公网检查只证明静态文件/匿名鉴权和留存 trace；没有将真实团队 token 下载到本机浏览器。

### 10 月 16 日发现的后续云端发布

中断期间云端又更新了运行版本。公开 observer 记录了 Codex、早晚报告、记忆提取和表达修复；11 个变化的 Python 文件，其运行指纹全部匹配 `feat/anker-assistant@2cc803e`。该分支部署说明指向 `/opt/evidenceguard-demo/releases/briefings-20261015/Cloud/server`、`70-briefing-runtime.conf`。本次初始 `50-demo-tools.conf` 和 Web 资源依旧存在，因此不能仅凭 Web 资源一致推断后端还是初次发布版本。

本分支已按逐文件内容同步相关后端，保留摄像头工具链；没有整分支引入其头像、手机连接应用 UI、签名或 TestFlight 发布工作。当前新增/保留的后端差异包括：

| 源码 | 后续云端行为 / 本分支处理 |
|---|---|
| `harness/codex.py`、`harness/runtime.py` | 正式 Codex App Server，限定工具、隔离进程/凭据、有限步数、不静默切回；保留本轮平台、工具确认与取消 |
| `harness/contract.py`、`harness/tools.py` | 只读 `read_home_report` 预览，不新增采集或通知订阅 |
| `briefings.py`、`personal.py`、`proactive.py`、`push.py` | 早晚订阅、时区与去重、真实来源/缺记录模板；旧每日概况迁移为单份，不自动新增订阅 |
| `memory.py`、`harness/providers.py` | 同一豆包模型的专用 JSON 提取、禁用该提取请求的深度思考、65 秒外层时限、持久重试 |
| `assistant_identity.py`、`harness/runtime.py` | 无摄像头也可正常身份/闲聊/记忆问答；持续观察能力和身份录入边界明确 |

本地更新后 **302 passed / 9 skipped**，含 5 项发布脚本测试。9 项跳过是 Linux Codex 的真实子进程/信号组测试，Windows 不能以 shebang 启动这个测试宿主；结构化输出、参数和其余后端测试仍执行。Mac 编译及硬件验收边界不变。

随后增加 11 项联调验收判据测试、8 项仅更新 Web 的部署/回滚测试，`Cloud/demo_release` 共 24 项通过；监控模块另有 5 项通过。`smoke.py` 按冻结的执行器分别核验：旧执行器要求真实模型 HTTP 200 记录，Codex 要求开始/完成事件、最终响应和两个只读工具的双重回执。Codex 的模型 HTTP 发生在子进程内，Python observer 未直接观测，因此不虚报 HTTP 次数或状态。缺少回执、出现其他工具或取图/控制均验收失败。

Web 新发现的兼容问题已修复：JSON 解码会保留新服务返回的隐藏早晚字段，旧版界面原样回传可能覆盖用户关闭每日概况的选择。现在只序列化可编辑的旧字段；四浏览器设置/记忆专项 8 项通过。iOS Codable 本来只编码其声明的旧字段，继续使用服务端旧版本兼容规则。

回滚脚本增加后续运行版本和高优先级 drop-in 检查；旧 backup 不能直接回滚上面新 release。原始 10 月 15 日备份仍保留，但常规操作必须先核对实时 ExecStart。

10 月 16 日 12:44（新加坡时间）AWS 会话恢复，SSM 再次确认实际运行路径为上述 `briefings-20261015/Cloud/server`。当前应用模块与 requirements 全部匹配本地；89 个云端应用/测试/依赖文件中，86 个相同，3 个仅测试有差异；本地另有测试补充。当前逐文件结果见 [10 月 16 日源码核对](CLOUD-REPOSITORY-COMPARISON-2026-10-16.csv)。原模型联调命令通过 `--resume` 取回完整 Success 回执，没有重复执行。

监控 collector 原先仍指向旧 tools release，因此显示的源码漂移不代表当前应用加载错误。新增 `web_release.py` 只更新 `80-demo-web.conf` 的 `EG_WEB_ROOT`，并将 collector 的 demo source 指向实际后端；不覆盖 60/70 的 Codex 配置、应用源码或数据。执行前要求运行源码逐文件匹配包内 manifest、没有活动 Agent/硬件操作；回滚备份检查后续配置/源码漂移，只恢复本次 Web 覆盖与 demo source。

### 10 月 16 日 Web 发布与验收

- 12:56（新加坡时间）SSM `2806431d-7977-44b9-be95-e536b2a4a2ca` 返回 Success。Web 发布目录为 `/opt/evidenceguard-demo/releases/tools-56389d827a535987/web`，后端仍为 `/opt/evidenceguard-demo/releases/briefings-20261015/Cloud/server`。本次发布前后 team/review 的 PID 相同。
- 新包 119 个文件；archive SHA-256 `56389d827a5359874c6370eb674e1f3074574b043d7b55528bb7a2c942c6b27b`；manifest 内容摘要 `dadca1c1fe6bd910bc14892140f726237276afeb065e415de15236043406b0c7`；打包基准提交 `86aaa75`。当前 59 份应用模块、contract JSON 与 requirements 全部匹配运行目录。
- 新包在 Linux 隔离环境 **306 passed**，包括先前 Windows 跳过的 9 项 Codex 子进程测试。生产数据库仅只读备份到临时库做迁移检查：skills 4、media/evidence 各 15、runs 48、recordings 1、personal_profiles 2、personal_memories 2、push_devices 1、connector_tokens 0、private_clients 6，迁移前后数量相同，quick_check 为 ok。正式库没有回写或恢复。
- 当前 Web 入口 `/assets/index-emoaA4TN.js` 的公网 SHA-256 与本地构建相同。Chromium、Firefox、桌面 WebKit、手机 WebKit 均通过公网入口、团队令牌表单和官方 SDK 切换检查，没有页面异常或横向溢出；未输入团队/设备凭据。
- 公网 `/`、SDK manifest、官方 Demo 入口均 200；匿名 `/api/bootstrap`、`/api/hardware/snapshot`、`/api/sdk/events` 均 401。修正 collector 后 `diskVsRunning=[]`、`processMatchesObserver=true`。`diskVsRepository` 仍以 Dashboard 自身声明的旧参考提交计算，不等同于本次逐文件对照结果。
- Web 配置备份：`/var/backups/evidenceguard-demo-web/20261016T045638379467Z`。没有为网页更新改动数据库。回滚逻辑通过故障注入测试，未在正式 demo 上故意制造故障或实际回退。

本次只更新 Web 的复现入口如下；此时不要运行旧的 `activate.py --release` 覆盖新后端：

```sh
/opt/evidenceguard-demo/venv-build10/bin/python RELEASE/preflight.py
/opt/evidenceguard-demo/venv-build10/bin/python RELEASE/web_release.py --release RELEASE
# 回滚先核对当前 ExecStart、drop-in 和源码指纹；若后续已发布其他更新，脚本会拒绝旧备份。
/opt/evidenceguard-demo/venv-build10/bin/python RELEASE/web_release.py --rollback BACKUP
```

另一独立会话随后更新了 Dashboard 观察器，独立重启服务；上述 PID/指纹是本次 Web 发布时点的证据。实际复核确认该次维护保留了全部业务源文件及本轮 `EG_WEB_ROOT`。旧的 Web 回滚备份因 observer 配置变化不应直接使用，后续发布重新记录配置。

### 最终同步发布与当前 Codex 联调

已合入同分支的 AWS 连接修复 `5ab4ec2` 和 Dashboard 正文查看 `1a2f7d8`，未强推。合并后重新通过 13 项 Web 单元、14 项监控测试、监控与当前后端的兼容脚本，以及 8 项受影响的桌面/手机 Dashboard 浏览器测试，TypeScript/Vite 生产构建成功。最终包内全部 94 个后端应用、依赖、测试及素材文件与 Linux 306 项通过的预检包完全同哈希，没有重复运行未变的后端测试。

- **当前 Web**：`/opt/evidenceguard-demo/releases/tools-78f9a46242aedff8/web`；入口 `/assets/index-3ay3CKUw.js`；最终四浏览器公网入口和官方切换复验均通过。
- **后端**：仍为 `/opt/evidenceguard-demo/releases/briefings-20261015/Cloud/server`。此次 Web 发布同时保留已上线的 observer `/opt/evidenceguard-dashboard/releases/51356eded710c92d`。
- **包**：119 文件，基准提交 `0c2153e`；archive SHA-256 `78f9a46242aedff813f667c252825e2361d57511d49aa03ccb01a7d06a07f2f9`；manifest 内容摘要 `00741bd4aee61b6ddd6be7c3ece44a7221ce2cd539fb205fcd6b8d570d596933`。
- **实际发布时间**：2026-10-16 13:23（新加坡时间），SSM `68e2d85e-2650-48a8-a3cd-41512114d2bc` 返回 Success；仅 demo 重启，team/review PID 在本次操作前后不变，业务数据保留。
- **对应回滚备份**：`/var/backups/evidenceguard-demo-web/20261016T052331630965Z`；使用同包 `web_release.py --rollback`。如观察器或后台配置此后再次变更，脚本会拒绝直接恢复，须先重新核对，不能绕过检查或回退数据库。

当前真实模型联调 SSM `f7751cbf-e261-4eac-9da0-e8ca6da5d061` 返回 Success：

| 请求契约 | run ID | 实际执行器 | 结果 |
|---|---|---|---|
| iOS | `demo-toolchain-ios-8d8f21d53ed648d7bd7266dbd0662b8f` | `codex-app-server-v1` | completed；两个指定只读工具均 completed |
| Web | `demo-toolchain-web-075172e3cb4b4c989af706f1c13155c1` | `codex-app-server-v1` | completed；两个指定只读工具均 completed |

两轮都核对了服务端冻结契约、`executor_started/executor_completed`、最终响应、API 工具回执和 observer 工具记录，工具为 `list_camera_capabilities` 与 `list_tasks`。测试安装关闭自动记忆，没有硬件操作或推送。当前登记设备和执行器设备均为 0，结果仅证明 HTTP/Agent/工具契约连通，不是 iPhone 二进制或物理摄像头验收。

当时 observer 尚未直接采集 Codex 子进程的模型 HTTP/提示词；`realModelCalls=null`、`promptSnapshots=0` 是明确的观测缺口，不能解读为未调用模型，也不填造 HTTP 200 次数。Dashboard 会话另行补充这部分采集，不影响本轮已核验的 Codex 生命周期与工具回执。
