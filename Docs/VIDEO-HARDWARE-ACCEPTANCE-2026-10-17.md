# 真机录像接入与检索验收 · 2026-10-17

本次完成真实录像入库、三种检索、云端 Agent 历史查询和 demo 发布；同时实现 iOS 官方事件下载→上传协调器及证据图片检索入口。iOS 原生接入与 Android 原片验收是两个不同的验证范围。

## 已验证的数据链

用户在官方 Android Demo 前台录制 T8171，进行放入红盖透明水瓶、调整位置、最终移走的操作。通过 ADB 取回保存的 MP4；没有把手机屏幕录屏、合成视频、事件缩略图或离散截图当成设备视频。

| 项目 | 本次材料 |
|---|---|
| 完整原片 | 295.231 秒，13,774,806 bytes，H.264 1920×1080 + AAC |
| 原片 SHA-256 | `9a0c1aa06b68a4cb1eb893ae25ca94df2a6b84aeb8dc99d09565765832813692` |
| 入库测试片 | 前 65 秒，H.264 1920×1080 / 15 fps、去音轨；5,768,291 bytes |
| 入库 SHA-256 | `b55698fa5d0f5492593f7f9b005e38baeffafdf0a5ac36566719847002eb9709` |
| 云端录像 | `video-c375d572c0cc44bd`，来源 `uploaded`，真实录像通过客户端导入 |
| 拍摄时间 | `recordedAt=null`；文件名、水印、导入时间不作为已核实的文件开始时间 |
| 索引 | v2；0–20、15–35、30–50、45–65 秒；4 视频向量 + 12 关键帧向量 |
| 向量模型 | `doubao-embedding-vision-251215`，1024 维 float32、归一化 |
| 核验模型 | `doubao-seed-2-1-lite-260915`，使用候选视频核对可见动作 |

原片解码时观察到重复 DTS 警告；测试副本统一时间基准后上传，原片未改动。所有下表时间都相对于 65 秒测试副本。人工按 0.5 秒间隔抽帧：放入位于 36–38 秒，最终移走位于 50.5–51.5 秒；中间还调整了几次水瓶位置，不是严格的“静置 10 秒”实验。

团队电脑的 `EvidenceGuard/output/Vector-Hardware-20261017/` 保存原片、测试片、参考帧、抽帧依据、`results.json` 和可播放的 `index.html`。该材料未提交到公开 Git；本机预览为 `http://127.0.0.1:8837/index.html`，仅限此电脑。模型调用及录像上传沿用授权 demo，未发布匿名录像链接。

## 真实模型结果

每次检索取 4 个候选、核验前 3 个；一个候选仍未核验。首批候选 378–1,039 ms，完整核验 10.85–17.41 秒；纯召回计算 0.79–3.27 ms。这是 16 条向量的小库，不能代表大规模吞吐。

| 查询 | 已核验结果 | 对应候选窗口 / 向量分数 |
|---|---|---|
| 有人把红盖透明水瓶放在桌面 | 匹配，约 37 秒 | 30–50 秒；视频余弦 0.4356，帧 0.4402 |
| 水瓶被拿走并离开画面 | 匹配，约 51 秒 | 45–65 秒；视频 0.4262，帧 0.3884 |
| 桌面上有红盖透明水瓶 | 匹配，约 38 秒；后窗也有持续存在 | 30–50 秒；视频 0.3675，帧 0.4168 |
| 仅参考图：第 40 秒画面 | 找到外观相似目标，37 秒 / 45 秒 | 两个水瓶窗口；视频约 0.706，帧约 0.767 |
| 参考图 + 水瓶何时被拿走 | 匹配，约 51.5 秒 | 45–65 秒；视频 0.7261，帧 0.6538 |
| 反例：一只猫走过桌面 | 0 个已核验匹配；2 个 uncertain、1 个 not_matched | 仍保留 1 个未核验候选，不能说完整录像已排除猫 |

余弦相似度不是概率；RRF 将视频和帧的排序融合，核验后再优先展示匹配项。纯图查询中空场窗口也有约 0.614 的视频相似度、0.623 的帧相似度，但视频核验未发现参考目标。因此不能设置一个未经标定的相似度阈值就声称“物体存在”。

已观察到模型误描述：放入查询的第二个匹配将调整位置描述成多次拿放；图文查询的空场候选误述“开头存在水瓶”，最终仍为 uncertain。报告保留原输出，没有筛掉这些问题。时间点为模型估计，原片回看仍必需；后续需补充多录像、遮挡、相似瓶子、短暂动作及未见过的负例，才可计算召回和误报指标。

## 云端 Agent 联调

最终发布后，通过与 iOS 相同的 HTTP 请求体调用 `/api/agent/runs`：`executionMode=history`、同一摄像头、`historyFilter.period=all`、同一参考图片 ID。请求来自本次验收脚本，不是假称 iPhone 已运行。

- 真实运行 `hardware-vector-162e45c3984240ee9bbc53aab977ebd9` 完成。
- 实际工具回执只有 `search_recordings`，返回原片约 00:51 的匹配、1 个未满足、1 个无法确认。
- `captures=[]`，没有调用实时取图或物理控制；历史工具契约没有授予现场控制能力。
- 原片接口 `Range: bytes=0-1023` 返回 206 和正确 Content-Range；发布后另测第二段 Range 同样通过。
- 换另一已认证安装实例后，原查询及参考图分别返回 404。原录像仍使用既有团队服务访问边界，不额外宣称个人隔离。

## iOS 新增实现

### 设备事件下载与导入

入口：设备 → 录像库 → 从设备事件下载录像。官方设备发现和 Token 登录方式沿用现有 SDK 连接。

1. 按设备及日期调用既有事件查询；仅展示 `hasVideo=true` 的事件。单次最多 50 条，未实现分页/全卡扫描。
2. 用户点选事件并确认将其上传到当前服务和检索模型。下载期间停止直播、排空硬件工具调用并暂停执行器认领；结束后恢复前台调度。
3. Kotlin 在缓存中再次校验事件 ID、设备 SN 与 `videoPath`，使用官方 `EventMediaPlayer(event, device).startDownload(path)`。无需先播放事件。
4. 等待 SDK Success，检查指定目录内本次 UUID 文件存在且不超过 150 MB；120 秒下载上限，释放播放器后预留 800 ms。失败/取消清理未完成副本，不处理设备原片。
5. Swift 再校验回执设备、事件、固定目录、文件名、大小和当前连接代次；135 秒桥接超时。服务切换、后台、离页或取消均阻止后续上传；已完成的服务端写入仍可在录像库查看。
6. 用现有 `registerSDKDevices` 和 `POST /api/recordings` 上传，随后建立 v2 索引。上传失败可在同一页面重试已下载文件；离页删除手机临时副本。
7. 事件时间仅用于标题；未验证事件起点等于文件第一帧，`recordedAt` 仍未知，不把事件时间或上传时间假作拍摄开始时间。

官方依据是主办方 `EventDataSourceImpl.downloadEventVideo`、`EventMediaPlayer`、`EventDownloadState` 与 `stopAndRelease`。产品桥接只接受其指定的保存路径；如果某固件/SDK 只返回其他回调路径，本版会明确失败，不擅自读取任意路径。这需在两款 iOS 真机分别核实。

这条链实现的是“官方可查询事件已有录像 → 手机 → Cloud”，不等于全天连续 SD 卡同步、断网补传调度、云端直读存储卡或在后台长期下载。T8214 仍是一台双摄门铃，当前导出内容按官方事件文件保留；尚未验证其主摄/下视是否独立导出。

### 证据图片进入历史检索

证据详情显示带鉴权的图片，增加“用这张画面查历史录像”。携带图片路径、来源摄像头、服务来源和入口说明，使用同源 API 读取并进入现有图文检索。图片可替换/裁剪，用户确认后才上传为查询图；不自动新建守护。切换服务或来源设备已移除时不继续加载旧证据。

### 源码位置

| 位置 | 实现 |
|---|---|
| `EvidenceGuard/EvidenceView.swift` | `DeviceRecordingImportView`、`RecordingLibraryView`、证据图片入口 |
| `EvidenceGuard/OfficialSDKConnection.swift` | `downloadEventRecording`、播放器/工具调度互斥、超时取消 |
| `EvidenceGuard/HardwareTools.swift` | 下载状态纳入前台执行器生命周期，结束后可重新登记 |
| `SDK/Bridge/EvidenceGuardSDKBridge.kt` | `downloadEventVideo` / `cancelEventVideo`、本地路径校验与原生资源释放 |
| `EvidenceGuard/APIClient.swift` | `uploadRecording(title:)`、同源图片读取与现有检索 API |
| `EvidenceGuard/VideoSearchView.swift` | `VideoSearchSeed` / `loadSeed`，复用检索与继续追问 |
| `Cloud/server/evidenceguard/app.py` | 转码未完成也能读取录像状态 |
| `Cloud/server/tests/test_video.py` | 排队、索引中、失败、中断且无播放文件的状态回归 |
| `Tests/CompatibilityAPI/APIClientTests.swift` | 上传保留设备范围与未知时间，跨源证据不发送请求 |

## demo 发布与回滚

先审查正在运行的实际 `--app-dir` 与三个环境的源码哈希，而非仅比较旧固定目录。合并原有守护/报告修复，首轮部署后再次合并 `dongrunze@80438af`，把团队提交的 SeedLite/v0.3/诊断代码保留在最终包中。SeedLite 模块随代码发布；配置和开关保持原值，没有新增启用或替换模型凭据。

- 最终 release：`/opt/evidenceguard-demo/releases/tools-4253361ffd4635a4`
- 内容哈希：`ac38688af6aa0414301ad7da40208c82f4990ea1fbbb148945ec6ad63e4c8f9a`
- 备份：`/var/backups/evidenceguard-demo-tools/20261016T185151546383Z`
- 初次升级前备份：`/var/backups/evidenceguard-demo-tools/20261016T183309238887Z`
- 业务数据库、原视频目录、认证配置与静态 Web 保留；team/review 进程未变。数据库副本迁移检查通过，业务行数保留。
- `capture_runtime.py` 只导出源码/配置哈希和进程路径；`package_runtime.py` 仅打包受 Git 管理的运行时、测试与固定提示词，不打包账号或录像。
- `runtime_release.py` 两次检查漂移，使用 release 内独立 venv，拒绝中断活跃 Agent/索引/检索，激活失败自动恢复。旧 drop-in、数据库一致性副本与 collector 配置保存在私有备份中。

回退到紧邻前一版，保留这次测试入库与之后的业务写入：

```bash
/opt/evidenceguard-demo/releases/tools-4253361ffd4635a4/venv/bin/python \
  /opt/evidenceguard-demo/releases/tools-4253361ffd4635a4/runtime_release.py \
  --rollback /var/backups/evidenceguard-demo-tools/20261016T185151546383Z
```

回滚程序有运行版本和配置漂移检查；出现其他人后续发布时会拒绝覆盖。它不会恢复旧数据库或删除录像。若要再退回最初升级前，须先完成上面的逐级回退，再使用初次 release 的回滚命令，不能跨越后来发布直接套旧备份。

## 验证范围与 Mac 接手

- 最终合并版本：Linux 后端 453 通过；Windows 443 通过、10 项 POSIX 专用跳过，已由 Linux 覆盖。
- 发布工具 30 通过；Web 单元 20 通过；TypeScript / Vite 构建通过。
- 本机 Chromium / Firefox / WebKit / mobile WebKit：200 通过、8 跳过。跳过涉及本机缺少可运行的官方 Web 构件/媒体测试条件；完整浏览器/系统兼容性仍看 CI，不把跳过算成通过。
- 修复 Dashboard 折叠内容检查、WebKit 媒体错误触发、长哈希换行及记忆测试启动重载竞态；保留团队新增的 iOS 脚本演示。未恢复产品 Web 的硬件开发路线。
- 本机没有 Xcode；新增 Swift/Kotlin 源码未在本机生成 iOS Framework。普通 iOS 模拟器 CI 只验证无官方 SDK 的产品 target，不能证明 arm64 桥接、真实事件下载或后台行为。

Mac 开发者先恢复官方包并执行 `python3 SDK/prepare.py --check`、`python3 SDK/prepare.py`，再编译 `EvidenceGuardSDK`，不能直接用旧 Framework。用 T8171 / T8214 各选择一条实际事件：验证 SDK 文件路径、完整播放、上传索引、失败重试、取消、后台切换、服务切换、工具停止与直播恢复。最后验证证据图入口、三个查询模式及返回原片定位，再归档/TestFlight。原 build 17 不包含本次改动。
