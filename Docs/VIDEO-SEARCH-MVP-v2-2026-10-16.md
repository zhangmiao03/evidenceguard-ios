# 视频检索 MVP v2：文档分析、实现与验收记录

日期：2026-10-16。依据团队提供的 `EvidenceGuard-视频检索MVP设计-20261016(1).txt`。

本轮完成仓库中的云端与 iOS 首版实现，并在 demo 所在服务器的隔离目录调用真实模型验证。没有替换正在运行的 demo 服务，没有上传 TestFlight。真实摄像头 1–2 小时录像、60 条留出查询及本版 iPhone 交互验收仍未完成，不能据此宣布最终质量验收通过。

## 1. 对方案的判断

方案可以建立在现有录像导入、播放、视频 Embedding 和视频核验基础上。需要改造的是检索与证据核验链路，而不是重新实现硬件 SDK。

- 文字、图片、图文是三种查询输入，共用一个业务检索服务。图文使用一次联合 Embedding 请求，不拼接或平均两个向量。
- 短视频索引负责寻找动作过程，独立关键帧索引补充外观检索。最终仍须播放真实原片，向量分数不证明事件发生。
- 当前已有的 SDK 事件图、前台直播采样不能代替整段录像。首版用真实 MP4 导入；SD 卡录像导出、自动续传和连续入库继续作为独立硬件集成事项。
- “先显示候选、再核验”是必要的交互变化：本轮真实模型耗时也说明不能让首屏等全部视频核验结束。
- 接口支持与检索准确率必须分别验收。四类输入返回合法向量，不等于在夜间、小目标、遮挡、相似物体等真实场景达到 Recall@10 指标。

本轮基线合入 `feat/anker-assistant@1ba73c5`，保留 `dongrunze` 的官方 SDK、双摄切换、停止未知结果及手机执行边界；`main@cc16c98` 已在分支历史中。产品 Web 不扩展新功能；Dashboard 仅更新只读索引观测兼容和私密内容过滤。

## 2. 实现范围

| 需求 | 本轮结果 | 源码 |
|---|---|---|
| 文本 / 图片 / 图文联合查询 | 已实现，联合输入只有一个 1024 维向量 | `video/providers.py`、`video/search.py` |
| 视频 + 关键帧索引 | 已实现，20 秒窗口、5 秒重叠；约 1 fps 候选帧，前中后三段各择一清晰帧 | `video/index_media.py` |
| 精确帧位置 | 使用 FFmpeg `showinfo` 的实际 PTS，按毫秒保存；不使用导入时间伪造拍摄时间 | `video/index_media.py` |
| 二进制向量 | SQLite 独立表、little-endian float32、1024 维、4096 字节、归一化校验 | `video/index_v2.py` |
| 幂等与恢复 | 同来源、机位、录制起点、摘要的重复上传复用文件；失败重试复用已完成向量单元 | `video/service.py`、`video/index_v2.py` |
| 原子发布 | 所需视频/帧单元完整后才切换该录像的活动签名；失败不会发布半成品 | `video/index_media.py`、`video/index_v2.py` |
| 召回 | SQL 先过滤来源、版本、摄像头和时间；NumPy 分块点积、每 clip 聚合、两路各 top 20、RRF | `video/index_v2.py` |
| 缓存 | 有界矩阵块 LRU，纯向量上限 64 MiB；发布/删除失效，范围与版本隔离 | `video/index_v2.py` |
| 候选与核验 | 默认返回最多 10 个候选，先发布；默认核验前 3、可设到 5，并发最多 2 | `video/search.py` |
| 原参考图参与核验 | 已实现。原图 + 原文 + 原视频共同核验；失败明确标记 | `video/providers.py`、`video/search.py` |
| iOS | 录像库和历史对话入口、照片/文件选图、目标裁剪、筛选、候选状态、原片定位、继续问助手 | `EvidenceGuard/VideoSearchView.swift`、`TeachAIView.swift` |
| 旧云端兼容 | `videoModels.retrievalVersion` 能力门控；旧云端隐藏提交能力，原历史对话保持可用 | `app.py`、`AppModels.swift` |
| 删除 | 删除录像、视频/帧索引和缩略图；旧查询不再返回其可播放卡片，显示库已变化 | `video/service.py`、`video/search.py` |
| 云端 Agent | `search_recordings` 调用相同业务服务，本轮授权参考图自动随工具传递 | `harness/tools.py`、`harness/runtime.py` |
| Dashboard | 识别已发布 v2 二进制向量；不导出私有参考图、独立检索正文和核验响应 | `Cloud/dashboard/eg_dashboard/`、`ops.py` |

表中 `video/`、`harness/` 均相对 `Cloud/server/evidenceguard/`。

没有在本轮实现：跨文件连续录像拼接、跨窗口额外 ±5 秒扩展、摄像头自动录像下载、多人家庭摄像头细粒度 ACL、ANN 集群、全天无限量入库。没有相邻真实媒体时不伪造连续录像。

## 3. 数据、模型和检索规则

### 3.1 入库

1. 上传上限保持 150 MB / 10 分钟。保留原文件、SHA-256、摄像头、来源及用户提供的 UTC 录制起点；新 iOS 同时传入来源时区。
2. 生成兼容播放 MP4；按 0–20、15–35、30–50 秒等窗口切片。
3. 每片一个视频向量；最多三张代表帧分别请求图片向量。完全相同媒体可复用向量，但仍保留每个 clip、帧时间和图片关联。
4. 每完成一个单元即持久化。重启后任务标记中断，用户点“重新建立索引”时复用已完成单元。
5. 完整性检查与活动签名、录像 ready 状态在一个事务中发布。已有当前版本重复索引不再次消耗模型请求。

新增表：`retrieval_recordings`、`retrieval_clips`、`retrieval_units`、`retrieval_embeddings`、`retrieval_index_jobs`、`retrieval_meta`。原 `recordings`、`video_segments` 保留，v1 JSON 向量不被 v2 覆盖。

### 3.2 模型与指令

本轮实际调用：Embedding 为 `doubao-embedding-vision-251215`；视频核验为 `doubao-seed-2-1-lite-260915`。模型 Key、地址及凭据只从部署环境读取，没有写入仓库。

Corpus 固定模板：

```text
Instruction:Compress the image into one word.
Query:

Instruction:Compress the video into one word.
Query:
```

查询统一 `Target_modality: image/video.`，文字、图片、图文分别使用目标/属性/动作检索、外观参照、外观加文字条件的指令。`image/video` 表示独立图片与视频样本混合库。

Corpus 签名包含网关、固定模型 ID、维度、采样及预处理版本；Query 签名单独包含查询指令版本。新查询不与旧 Corpus 向量混用。视频核验提示词另行约束：动作要直接看到过程；外观只能证明可见相似性；`eventTime` 必须是单个数值或 null，持续区间写入 `events.start/end`。

官方依据：[多模态向量化 API](https://docs.volcengine.com/docs/ark/multimodal-vectorization-api?lang=zh)、[联合输入说明](https://docs.volcengine.com/docs/ark/vectorization?lang=zh&redirect=1)、[Query/Corpus 指令规则](https://docs.volcengine.com/docs/vector_database_vikingdb/VectorLibraryInstructionparametersetting?lang=zh)。这些支持接口用法；窗口、排名和验收阈值仍是项目选择。

### 3.3 召回、缓存、核验

- 每块最多 1024 条向量，约 4 MiB；批量点积在工作线程执行，召回并发为 1。超过 1 万条继续分块，不静默截断。
- 视频路每 clip 一个分数；帧路每 clip 只取最佳帧。分别取前 20，按 `1/(60+video_rank)+1/(60+frame_rank)` 融合。
- 同一录像、同摄像头的高度重叠窗口去重；最终同一匹配时刻也合并原始命中区间。不同时间的事件仍可各自保留。
- 矩阵缓存按数据库 generation、Corpus 签名、摄像头、来源、日期范围隔离，不含用户查询向量。不缓存最终查询结果，也不复用过期搜索结果。新请求总是重检元数据。
- 没有统一相似度阈值；卡片先是“相关候选”。`matched`、`not_matched`、`uncertain`、`verification_failed` 分开，未复核候选继续保留。
- 核验时间必须落在 clip 和用户时间范围内。范围外动作不算匹配，范围外关键帧不做该次查询缩略图。
- 模型/网络失败不会写成“没有发生”。检索没有返回结果也只说明已入库范围的缺口。

## 4. 权限边界与 API

当前摄像头录像仍是**服务内团队共享**数据，沿用 prod/review/demo 各自数据库和访问令牌隔离；不是已实现的家庭成员 ACL。官方模式还要求摄像头在本服务登记，来源为官方接入或相应机位的人工导入。登记不等于独立验证官方账号所有权。

参考图和搜索任务另外绑定 `X-EG-Installation-ID` + `X-EG-Private-Key`。仅伪造安装 ID 不能读取他人图片/任务；没有可信私有凭据不能使用新搜索接口。原片读取继续使用团队鉴权/媒体 Cookie，并检查相同的官方来源可见范围。

| 方法与路径 | 用途 |
|---|---|
| `POST /api/video-search-images` | 二进制图片上传，最大 5 MB；服务端校验 JPEG/PNG/WebP、像素上限，移除 EXIF、转 JPEG；返回受授权引用 |
| `GET /api/video-search-images/{id}` | 当前安装实例读取参考图，私有响应，不公开缓存 |
| `POST /api/video-search` | 创建检索，立即返回 `searching` 和查询 ID |
| `GET /api/video-search/{id}` | 读取候选、核验进度、结果、筛选快照、耗时、库变化提示 |
| `GET /api/video-search/{id}/thumbnails/{clip_id}` | 当前查询的合法范围内命中帧；不存在范围内帧则 404，不拿范围外图片充当证据 |
| `GET /api/recordings/{id}` | 录像元数据，受来源范围检查 |
| `GET/HEAD /api/recordings/{id}/video` | 原片播放版本，保留 Range/206 与 AVPlayer 定位 |
| `POST /api/recordings/{id}/index` | 重试/建立 v2 索引 |
| `DELETE /api/recordings/{id}` | 用户明确删除当前服务的录像及索引；正在索引或用于活动回放时拒绝，不操作 SD 卡 |
| `POST /api/agent/runs` | 新增可选 `referenceImageId`，限历史模式并校验图片归属 |
| `GET /api/bootstrap` | `videoModels.retrievalVersion=2` 表示新版检索；`embeddingReady` 表示模型配置就绪，不代表已有可检索录像 |

请求示例（不包含实际图片、摄像头 ID 或凭据）：

```json
{
  "text": "有人把这个背包放到门边",
  "image_ref": "query-image-00000000000000000000000000000000",
  "camera_ids": [],
  "time_range": {"period": "yesterday"},
  "timezone": "Asia/Shanghai",
  "limit": 10,
  "verify_limit": 3
}
```

`text`、`image_ref` 至少一项。引用必须来自当前实例的真实上传回执，不能直接使用示例值。自定义范围用 `period=custom` 和 UTC Unix 秒 `startAt/endAt`。App 的日期筛选是硬范围；直接检索不会暗自把文字里的日期转换成更大范围。

结果状态包括 `searching`、`verifying`、`completed`、`no_recordings`、`no_indexed_recordings`、`no_candidates`、`failed`、`interrupted`。候选包含真实录像/片段 ID、播放 URL、命中帧 URL、片段范围、定位秒数和核验状态；不返回服务器路径。排序细节保留在 API 供排查，产品页面不显示向量、内部 JSON 或余弦百分比。

公开只读 Dashboard 与私有参考图边界分开：即使打开内容采集，新检索上下文也只留下模型、状态、用量及耗时；不会复制参考图到 Dashboard 的公开媒体缓存。私有图片当前保留在本服务，不设置未经用户选择的自动保留期限。

## 5. iOS 使用与 Mac 交接

入口：**摄像头 Skill → 录像库 → 用文字或图片检索录像**，或助手切换历史模式后从菜单进入。

1. 导入同机位的真实 MP4，选择摄像头；知道实际开始时间再填写。
2. 等索引就绪，或对旧索引点击“重新建立索引”。旧索引不会自动产生新的关键帧。
3. 写文字、选一张照片/图片文件，或两者一起；可裁剪并放大目标。服务端使用实际提交的裁剪图。
4. 选摄像头与时间。参考图、原问题和实际范围留在结果区域。
5. 候选出现即可播放，随后更新核验状态；进入播放器复用原片定位和前 3 秒回看。
6. “带着本次条件继续问助手”保留原参考图、摄像头和已解析的绝对日期范围；图片引用参与请求重试身份，不能把换图后的请求误当作同一轮。

切换服务时清除本页旧搜索结果，不把旧服务器图片引用带到新服务器。新版 UI 检查能力字段，旧服务未开放时给出升级提示。

`VideoSearchView.swift` 已加入 `EvidenceGuard` 和 `EvidenceGuardSDK` 两个 target。Mac 需执行：

```sh
bash scripts/check_mobile_contracts.sh
bash scripts/test_ios_compatibility.sh
# 真实 SDK 按既有 README 恢复 Vendor/私有配置，再检查 arm64 构建和真机。
```

新增 `Tests/VideoSearch/main.swift` 检查请求/响应、旧服务兼容和带图片的重试持久化。当前 Windows 无 Xcode；项目结构检查与云端测试不等于 SwiftUI 编译通过。照片选择/裁剪、VoiceOver、动态字体、断网恢复、切换服务、AVPlayer 定位和真机设备仍须用新安装包验收。

## 6. 本轮测得的结果

环境：demo 同机的隔离虚拟环境和临时数据库；真实网关；不读取家庭原片、不改运行服务。合成素材是 4 秒静态蓝色矩形，只有一个候选片段，不能代表真实录像检索效果。

| 检查 | 结果 |
|---|---|
| 文字、图片、图文、视频 Embedding | 均返回合法 1024 维向量；归一化通过 |
| 同图修改文字 | 联合向量发生变化，说明网关实际传入文字条件 |
| 原片 → 视频/帧索引 | ready；最新一次约 2.20 秒 |
| 文字候选 / 完整核验 | 约 404 ms / 3.36 秒 |
| 图片候选 / 完整核验 | 约 991 ms / 4.69 秒 |
| 图文候选 / 完整核验 | 约 485 ms / 4.23 秒 |
| 先候选后核验 | 三种查询均观测到 |
| 1 万向量无矩阵缓存 | 30 次：P50 381 ms、P95 709 ms，未达目标 |
| 加缓存后 1 万向量 | 30 次热召回：P50 48 ms、P95 75 ms；纯向量缓存 39.06 MiB，进程峰值约 104 MiB |

上表为服务器内部计时，不含手机上传、无线网络与 2 秒轮询等待，也不是 1–2 小时真实视频的产品延迟承诺。矩阵基准使用 2500 clip / 10000 合成向量、`OPENBLAS_NUM_THREADS=1`；默认大线程池的结果不能直接套用。

早期两轮同一图文样例中，模型将 `eventTime` 写成字符串区间 `"0-4"`，均被严格拒绝并显示复核失败。补充“单个 JSON 数值、持续区间独立填写”的提示词后，最新三种查询都返回合法 matched 回执。这里验证的是链路与格式；旧失败记录不能从质量统计中抹去。

测试覆盖维度/数值拒绝、原子发布、断点复用、重复上传、两路召回与时间去重、版本与摄像头过滤、跨午夜时区、图片私有凭据、先出候选、范围外核验、删除/缓存失效、旧版回退、Dashboard 私密媒体保护等。

| 最终源码验证 | 结果 |
|---|---|
| Windows 后端全量 | 349 通过、9 个 POSIX 相关跳过 |
| WSL Ubuntu / Python 3.12 后端全量 | 358 通过、无跳过；包含实际 FFmpeg 抽帧/索引恢复测试 |
| Dashboard 单元测试 | 29 通过 |
| 发布 / 回滚测试 | 24 通过 |
| 既有 Web | TypeScript / Vite 构建通过，未新增产品功能 |
| iOS 项目与 SDK 宿主 | xcodeproj 结构解析通过；新页面同时加入两个 target；宿主 plist 检查通过 |
| Swift / Xcode / 真机 | 未执行；不能用项目解析代替编译 |

复测时 Windows 与 WSL 曾并行使用默认数据目录，WSL 在测试收集阶段发生 SQLite WAL 磁盘错误；改用 Linux 独立临时数据库与字节码目录后全量通过。跨平台测试应分别设置 `EG_DATABASE`，不要并发打开共享挂载目录中的同一 SQLite 文件。测试还报告一条 Starlette/AnyIO 的弃用警告，不影响本轮结果。

## 7. 验证命令与真实资料验收

先安装更新后的 `Cloud/server/requirements.txt`，系统 PATH 提供 FFmpeg/ffprobe。真实模型冒烟测试只使用脚本生成的合成媒体：

```sh
export PYTHONPATH=Cloud/server
export OPENBLAS_NUM_THREADS=1
export EG_ENV_FILE=/path/to/private/cloud.env
python -m evidenceguard.video.probe --output /private/path/probe.json
python -m evidenceguard.video.benchmark
python -m pytest -q
python -m unittest discover -s Cloud/dashboard/tests
```

真实质量验收仍需要同机位 1–2 小时、包含目标/动作/夜间/遮挡/相似干扰的导出录像。每种查询至少 20 条，含正例和无结果例；参考照片优先来自不同时间或视角。调参和留出样本按录像/事件分离。

`video/evaluate_search.py` 提供评测入口。在数据库及完整媒体目录的**私有副本**上运行。v2 将片段和帧保存为媒体根目录下的相对引用，可随副本搬迁；旧 v1 索引仍按其原有路径规则恢复。该程序不替你获取录像或生成真实标签：

```sh
python -m evidenceguard.video.evaluate_search \
  --manifest /private/evaluation/cases.json \
  --database /private/snapshot/app.sqlite \
  --media-root /private/snapshot/recordings \
  --output /private/evaluation/results.json
```

每个用例包含 `id`、`mode(text/image/joint)`、`split(tuning/held_out)`、`event_group`、查询 `text/image`（图片路径限评测目录内）、`camera_ids`、`time_range`、`expected`。标注项为 `recording_id/start/end/kind(appearance/action)`，无结果用空数组。标注仅评分，不发送给模型。程序分别记录 Recall@10、外观/动作召回、定位正确的确认、负例误确认、无法确认和服务失败；不足每类 20 条不会标为足量，语义描述正确性仍需人工复核。

尚待达成：真实留出集 Recall@10 ≥90%、动作核验正确性、无结果误确认率、正常手机网络首批候选 2–5 秒目标、iPhone 新版构建与实际回放。没有真实标注数据时不报告这些指标已通过。

## 8. 部署与回退

1. 先备份业务 SQLite 与媒体目录，升级依赖并保留旧 release / 虚拟环境；不要直接覆盖团队正在使用的云端修复。
2. 新代码默认 `EG_VIDEO_INDEX_V2=1`；先在 demo 的副本导入小样本，检查 bootstrap 能力、三种查询和媒体鉴权，再逐文件重建旧索引。
3. 当前代码内可设 `EG_VIDEO_INDEX_V2=0` 回退到旧文字视频检索。只有本来就有 v1 索引的录像能立即使用旧版；v2 新增录像不会凭空拥有 v1 向量。旧表不删除。
4. 若整体回退 release，连同对应依赖环境和服务配置一起恢复；不要将不完整 v2 索引当作旧版索引。
5. 本轮隔离实测目录与业务服务隔离，没有自动迁移全库、发布新服务或上传 TestFlight。

原先的官方 SDK 切换、Token 直连、T8171 云台和 T8214 双摄实现保持原路线。录像检索消费已经取得的媒体；它没有扩展官方 SDK 的硬件能力，也没有把 Dashboard 变成硬件执行器。
