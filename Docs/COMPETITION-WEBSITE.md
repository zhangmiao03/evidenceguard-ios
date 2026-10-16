# 比赛网站发布与验证

当前维护状态（2026-10-16 19:28，新加坡时间）：运行版本为 `6b749dfdf54d6830`，保留上一版 `073ca161a4de655e` 供回滚；唯一有效的版本回滚配置是 `/var/backups/evidenceguard-dashboard/20261016T112647276589Z`。文末记录了中间版本清理，前文早期发布路径仅供历史追溯，已清理的目录不能再用于回滚。

## 页面入口

| 用途 | 地址 |
| --- | --- |
| 比赛作品 / iOS 交互展示 | https://demo.47.131.21.137.sslip.io/dashboard?view=showcase |
| 真实运行监控 | https://demo.47.131.21.137.sslip.io/dashboard |
| 图片分析 | https://demo.47.131.21.137.sslip.io/dashboard?view=images |
| 视频向量库 | https://demo.47.131.21.137.sslip.io/dashboard?view=vectors |
| 完整网站 ZIP | https://demo.47.131.21.137.sslip.io/dashboard/downloads/evidenceguard-website.zip |

同一网站的所有监控页可切换 demo / team / review 环境。`http://47.131.21.137/dashboard` 仍可使用；HTTPS 使用匹配证书的域名。App 产品入口与鉴权继续独立存在。

## 空数据原因与修复

2026-10-16 实测 IP HTTP 返回 Dashboard 数据；demo HTTPS 可以打开 HTML，但 `/dashboard/api/info` 返回 401，其他 TLS 入口也路由到 App 服务。旧前端吞掉发现接口错误，所以不同访问地址出现“有人有数据，有人空白”。

`eg_dashboard/nginx_routes.py` 只在每个既有 TLS server 中增加带标记的 `/dashboard` 与 `/dashboard/` location，转发到 127.0.0.1:8795。原 `/api`、上游、证书、HTTP 跳转保持原值。修改前备份，nginx 检查失败即还原；重复部署不重复添加。`activate.py` 将这三个文件纳入回滚清单。

前端同源匿名读取，不转发 App 密钥。401/403、HTML fallback、超时均明确显示；自动重试从 3 秒递增至 30 秒，连上后每 5 秒取快照。环境切换清空筛选；筛选后无记录可一键恢复。失败保留旧数据并标记过期，不显示成新的正常结果。

另发现客户端轮询高峰会将旧视觉调用挤出最近 3,000 条快照。现在额外读取最近 20 组 Agent / 模型 / 图片 / 视频 / 嵌入 Trace（最多 240 条、2.5 MB），按原 ID 去重并保留真实时间；总导出仍受 6 MB 上限约束。`coverage.visualTraceSupplement` 明示采集范围与截断，不补造未记录的调用。

## 数据来源与边界

图片页读取 `sdk_episodes` 的结构化 `review`、`evidence.reviewStatus/reason`、`visual_cache`，并列出已观测的 `image_review`、`frame_presence`、`video_verify` 模型记录。状态以数据库当前状态列为准，避免 payload 中旧 pending 状态覆盖实际 completed。核验文字与未知项可展开；库中结果可能早于采集启用，不能补造历史提示词。模型详情继续使用已有完整正文查看器。

视频页读取 `recordings` 与 `video_segments`。展示实际模型、索引签名、片段起止时间、维度、范数、归一化状态、前 16 维数值、向量 JSON 的 SHA-256。采集器从当前运行进程获取 embedding signature，旧签名明确不匹配；进程身份不一致或缺少配置则显示未知。签名匹配不等于语义正确，也不是模型置信度。统计区区分库内总数、当前筛选和受限采样。

每张表最多 120 条，采集保持只读并使用同一数据库读取事务；缺表是未知，空表是 0。根据比赛公开展示需求，记录引用的图片与录像现在通过独立媒体缓存展示；外部签名 URL、源文件路径和凭证仍不进入公开投影。原始视觉分析仅针对离散图片，不证明连续状态。服务器已有 `synthetic_review` 录像是合成测试素材，其真实入库和向量结果与素材真实性分别标注。

### 媒体、模型输入与检索记录（2026-10-16 更新）

- 图片：`sdk_events`、关联的 `sdk_episodes`、`evidence` 从实际 `imageUrl` 所引用的 `media` 行取原图；不按时间邻近猜测关联。支持放大及单独下载。历史事件来源图不标为当次模型输入。
- 豆包输入：`EG_DASHBOARD_CAPTURE_MEDIA=1` 与正文采集一起由部署脚本开启。真实模型 HTTP 请求发出前，在后台线程复制其中的 JPEG/PNG/MP4 data URL，按 SHA-256 记录 `inputMedia`；请求本身不修改、不重试。输入引用与提示词 ID、模型返回保持同一 Trace。旧输入不能追溯恢复，页面明确显示缺失。URL 类型输入不自动下载。
- Codex 执行器：当前 demo 主后端使用 `codex-app-server-v1`。在 `complete` 的实际 messages 入口保存图片副本，并标记 `executor_input` / `host_to_codex`；展示的是传给执行器的字节，不能声称看到了底层发给豆包的 HTTP 报文。执行器之后可能进一步转换图片。普通 HTTP 模型调用仍标记 `exact_model_input`，两种来源分开说明。包含图片的执行器 Trace 也进入视觉保留范围。
- 录像：仅复制已入库录像目录的 `playback.mp4`，支持浏览器播放、Range/206 拖动和下载。超过 32 MB 的副本不公开，界面显示不可用；不开放任意文件或原 App 的受保护媒体接口。
- 检索：观察实际 `VideoService.search`，采集 `vector.search` 的查询文字、参数、范围、候选相似度、视觉复核结果、定位秒数与耗时。不增加检索、不改业务返回或异常。兼容既有 `search_recordings` 工具回执。当前后端查询入口只实现文字搜视频，图片向量输入展示区在没有真实调用时明确为空，不伪造以图搜视频。
- 技术信息：列表优先显示设备类型/名称、任务含义和时间。原始 ID、签名、向量摘要保留在详情，供开发核对。

安全与容量：每次调用最多 6 份媒体；图片 8 MB、视频 32 MB；每环境公开媒体最多 160 项 / 160 MB，私有输入目录和公开目录各自容量上限 256 MB。只读采集器按记录引用复制，写入当前允许清单。匿名 HTTP 进程只能从此清单提供媒体，不能访问 App 数据库/环境文件；不在当前清单的旧副本立即不可访问，缓存文件稍后清理。快照导出只含本机同源媒体引用，不嵌入媒体字节；离线主机无法凭引用恢复真实素材。

## iOS 交互展示

团队确认的硬件边界：摄像头控制只能由手机 App 的官方 SDK 执行。Dashboard / 浏览器手机预览没有这些硬件控制接口；不以网页模拟手机、后端代理或工具名称来宣称能够配网、绑定、控制云台或对讲。数据链路为手机 SDK 获取媒体及设备回执 → 按需上传 Cloud → Agent 分析与检索 → Dashboard 只读展示。页面中的状态切换只改变演示脚本，不向真实设备发命令。

新版复用 `EvidenceGuard/Assets.xcassets` 内已有的 JPG 场景与头像，在 Web 构建中一并打包；不用占位简笔场景图。字体尺度、蓝白配色对照 `DesignSystem.swift`，五个标签对照 `RootView.swift`；补齐一致的 SVG 图标、系统状态栏、安全区、分组卡片和开关。场景照片是设计素材，预览内的状态仍是演示脚本，不是当前设备画面。

浏览器复现当前产品的五个入口：助手、摄像头 Skill、任务、记忆、我的。可选择门口包裹、室内宠物和工作室；需求→确认创建 Skill→对象可见/离区/遮挡→任务证据→继续追问→添加/删除偏好→暂停/恢复/重置。“手机 SDK 说明”只展示上述边界，不加载 SDK、不申请硬件权限。所有变化只在浏览器内存，刷新恢复初始值。

它不是原生 iOS Simulator，不编译 Swift，不验证 arm64 SDK、真实摄像头取流、云台或对讲。预览对话是有明确标记的离线脚本，不伪装成真实模型调用。真实运行应从左侧 Trace / 图片 / 向量 / 服务器页面核对。

## 构建与发布

```powershell
npm --prefix Web run build -- --base /dashboard/
python -m unittest discover -s Cloud/dashboard/tests -v
npm --prefix Web test
cd Web
npx playwright test tests/browser/dashboard.spec.ts tests/browser/showcase.spec.ts tests/browser/media-preview.spec.ts tests/browser/judge.spec.ts
cd ..
python Cloud/dashboard/build_release.py
python Cloud/dashboard/upload_release.py Cloud/data/deploy/dashboard.tar.gz --no-system-proxy
```

上传器返回 release 目录后，通过 SSM 执行该目录的 `activate.py --release <同一目录> --capture-content`。它先验证实际部署的两套代码，保留当前业务 ExecStart 和发布目录，仅替换 observer 与 Dashboard，逐个重启服务并验证原 API 鉴权。部署后运行 `python Cloud/dashboard/verify_public.py`，覆盖三套 HTTPS Dashboard、实时快照、ZIP 下载与原 App 401。

`Cloud/data/deploy/evidenceguard-website.zip` 包含根入口、`dashboard/index.html`、编译后的 JS/CSS 和说明。上传整个解压目录到静态主机根目录即可；本地可 `python -m http.server 8080` 后访问根页面。不要用 file:// 双击替代 HTTP 模块加载。静态主机的监控页支持导入脱敏追踪 JSON；若要实时监控，配置同源 Dashboard API 反向代理。ZIP 不包含密钥、云端数据库、真实媒体或离线真实数据副本。

部署包 `dashboard.tar.gz` 附带只读 Python 采集服务与回滚脚本；它用于当前 AWS 服务部署，不是静态托管上传包。真实后端代码不会被这两个包覆盖。

## 本次验收记录（2026-10-16，新加坡时间）

- 实现提交：`49642c5`；视觉 Trace 补充修复：`6a99a9e`，均已推送至 `dongrunze`。
- 最终服务目录：`/opt/evidenceguard-dashboard/releases/5601b0e41dc659b4`；部署包 SHA-256：`5601b0e41dc659b435877ed0c50cd2a6283dc062a647e96e6351093ff55947e5`。
- 17:51 部署的回滚目录：`/var/backups/evidenceguard-dashboard/20261016T095146570861Z`。仅对本次 Dashboard/observer 配置回滚，不替换业务代码。
- 网站 ZIP SHA-256：`b3cb90f28da5373e54f9acdb4b56876e2dc4607978884cb046de4ea7e6108bbe`，线上下载内容与本地包逐字节一致。
- Python 监控测试 23 项；Web 单元测试 16 项；桌面 Chromium/手机 WebKit 共 16 项，新增页面在 Firefox/桌面 WebKit 再验证 6 项，均通过。生产构建通过。
- 服务器实际两套业务树、各自元数据/正文模式，共 4 次兼容检查通过；其中模型循环用隔离测试响应，不计作生产模型调用。三套服务 health 200、原 App 未鉴权 API 401、Dashboard 写请求 405，HTTPS 页面与快照均 200。
- 线上 demo 实际数据：7 组 SDK 图片事件核验、12 条视觉缓存；额外保留的 7 组图片 Trace 共 28 条，均有真实 `image_review` 模型记录、关联提示词和返回正文，未截断。视觉模型为 `doubao-seed-2-1-lite-260915`。
- 线上向量：1 段 10 秒 `synthetic_review` 测试录像，Embedding 模型 `doubao-embedding-vision-251215`，实际向量 1024 维、范数 1、当前签名匹配。没有把测试素材说成摄像头实拍。
- 已在内置浏览器打开正式网址，检查图片分析正文、向量库和 iOS 展示；独立静态 HTTP 服务也可打开 ZIP 根入口。真实摄影与模型结果来自既有后端记录；本次没有声称重新完成原生 iOS 编译或硬件取流验收。

## 媒体与手机展示追加验收（2026-10-16 18:58 部署，新加坡时间）

- 媒体 / 视觉实现提交 `0993957`；执行器图片采集修复 `f8708d1`。已同步队友的 `ae5d71c`，保留其原生 iOS、SDK 与业务后端更新，并推送 `dongrunze`。
- 当前发布目录 `/opt/evidenceguard-dashboard/releases/073ca161a4de655e`；部署包 SHA-256 `073ca161a4de655ee6d25909fcd0cc01488523dd156bc6799fffe68eb903386f`。回滚目录 `/var/backups/evidenceguard-dashboard/20261016T105814535684Z`。
- 网站 ZIP SHA-256 `136989ba91bbd0fc58509891569e374038643c00fe198853be849b7e8fbc620c`，已比较线上下载与本地产物，逐字节一致。
- 合并后生产构建、28 项 Python 监控测试、16 项 Web 单元测试、40 项 Chromium / Firefox / WebKit / 手机 WebKit 浏览器测试全部通过。服务器再次通过四组实际业务树兼容检查；三套服务健康、原 App API 鉴权、匿名 Dashboard 和只读限制均通过。
- demo 实际任务 `dashboard-media-9ba6dcae942543b689ba8902a1f2da69` 完成：`read_stored_image` → Codex 执行步骤（`doubao-seed-2-1-lite-260915`）→ 最终回复。其 24,290 字节 JPEG 输入副本 HTTP 200、SHA-256 与观测的输入一致；同一 Trace 的工具、模型输入和最终回复都有正文。该图片是已保存的 SDK 事件图片，不是本次实时取景。
- 上述图片观察边界是 `host_to_codex`，页面标注“传给 AI 执行器的原图”；不将执行器记录解释为可见的模型底层 HTTP 报文。
- review 实际任务 `dashboard-media-fb91df4a49f14c8c83b8e9ca25f85923` 完成：`search_recordings` → `doubao-embedding-vision-251215` → `doubao-seed-2-1-lite-260915` 视频复核 → `vector.search` → 最终回复。查询“包裹离开区域”返回一个候选，余弦相似度约 0.2635，复核为 uncertain。页面保留“无法确认”，不改写成确定发生。
- 检索使用服务器原有 10 秒 `synthetic_review` 合成录像，页面显示“非摄像头实拍”；已在内置浏览器从开始实际播放到 10 秒结束，解码尺寸 640×360，媒体无错误。普通 HTTP 视频复核的实际输入也有独立副本记录。
- demo 公开缓存的 11 项去重媒体（10 图、1 视频）均验证返回 200、内容 SHA-256 一致、字节 Range 返回 206。模型图片放大、输入/结果关联、无任意外链请求由浏览器测试覆盖。
- 查看本次检索：在视频向量库将“后端环境”切到“Apple 审核”；查看真实图片识别：选择“手机演示”。不同环境的数据保持隔离，不为了展示而复制成另一套环境的记录。
- iOS 展示使用项目自有场景照片，五个入口可交互，仍是有标记的浏览器演示。本次验收不等于原生 iOS 构建或真实设备取流测试。当前业务未实现图片作为向量查询输入；相关空态明示这一边界。

## 手机 SDK 边界与空间清理（2026-10-16）

- 提交 `b9b0c81`：将展示入口改为“手机 SDK 说明”，明示摄像头控制统一在手机 App 官方 SDK 执行；Web 展示不具备这些接口。README 与本页同步。已通过生产构建及四种浏览器的完整演示交互检查，预览没有业务写请求。
- 19:26 新发布目录 `/opt/evidenceguard-dashboard/releases/6b749dfdf54d6830`；部署包 SHA-256 `6b749dfdf54d683093f40a3dbac1c02dca1a1b07cb056ff44ae8b658dd911461`，网站 ZIP SHA-256 `6fec7f266b1523020f19250c8509a2d41984e50d8c9a7e526113f77301ff38c2`。
- 先只读检查实际 systemd 配置、进程引用、采集配置与回滚 manifest，形成固定清单；执行前再次核对目录身份、内容规模与引用未变化。删除范围限定为 Dashboard 的发布目录、对应上传分片、过期版本回滚配置，拒绝符号链接、跨挂载或超出范围的路径。
- 已删除 9 个旧 release、11 组 `/tmp/eg-dashboard-upload-*` 分片、9 份过期版本回滚目录，共释放 17,858,560 字节（约 17 MiB）。磁盘仍约 24 GiB 可用、占用 16%。没有清理业务源码、数据库、录像、图片或模型运行记录。
- 保留当前 `6b749dfdf54d6830`、上一版 `073ca161a4de655e` 及 `20261016T112647276589Z` 回滚配置；独立的原 HTTPS 路由备份 `https-20261016T082200Z` 仅 8 KiB，继续保留。
- 当前版本的回滚命令：`python3 /opt/evidenceguard-dashboard/releases/6b749dfdf54d6830/activate.py --rollback /var/backups/evidenceguard-dashboard/20261016T112647276589Z`。已确认所引用的上一版文件完整；本次没有实际执行回滚。
- 清理后五个相关服务均为 active，三环境 Dashboard/健康接口、原 App 未鉴权 401、Dashboard 写请求 405、媒体与向量表均通过复核。清理结果保存在服务器 `/var/tmp/evidenceguard-dashboard-cleanup-result.json`；清单在同目录的 `evidenceguard-dashboard-cleanup-plan.json`。
- 后续部署完成验证后按“实际使用中的版本＋上一可回滚版本”保留；先核对真实引用及回滚依赖再清理。未设置无人值守的定时删除。
