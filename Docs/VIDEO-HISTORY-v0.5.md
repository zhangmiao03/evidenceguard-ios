# v0.5：历史录像检索与原生播放

## 已实现的闭环

原生 App「AI → 历史回顾」输入问题 → `search_recordings` → 视频 Embedding 召回 → Lite 观看候选视频复核 → 带结果和时间点的证据卡 → AVPlayer 播放原录像的对应位置。

「查录像」只把示例问题填入可编辑输入框，点击发送才执行。「录像库」可选摄像头、导入本地视频、查看索引状态、重试索引、打开播放器。真实采集时间可填；未知时留空，不能把导入时间冒充拍摄时间。文件导入 UI 已编译，当前实测样片通过 CLI 导入；本轮 App 验收覆盖发问、返回证据卡及播放。

## 实际视频验证

**结论：链路已跑通，Lite 仍存在明显内容幻觉，暂不通过自动守护的模型可靠性验收。**

本轮用 3 段公开拍摄录像建立 4 个片段的向量索引，标题使用 A/B/C，不把数据集标签或文件名作为模型判断依据。

| 样例 | 时长 | 可观察内容 | 验证情况 |
| --- | --- | --- | --- |
| A（t4） | 8.03 秒 | 人从 SUV 下车，走向门廊，拿起长纸箱，带回车内 | 检索排名第一；Lite 定位约第 5 秒；人工查看连续帧和 App 播放确认拿起、带走顺序 |
| B（d1） | 9.68 秒 | 人抱包裹进入门廊遮挡区，再空手离开 | 放下动作有遮挡；初次模型过度推断，增加可见性约束后单独复核为无法确认，不作为“放下动作已验证” |
| C（o1） | 29.58 秒 | 人持包裹在门前操作，局部遮挡 | 拿取查询的候选，模型无法确认；不能当作拿走现场包裹的证据 |

首次查询“包裹什么时候被拿走”时 A/B/C 向量相似度约为 0.407/0.314/0.291。相似度仅用于排序，不是置信概率。A 返回原片第 5 秒的可播放卡片；B 是非匹配候选，C 为无法确认。原生播放器已实际加载视频并跳转到动作附近，见 [播放验收截图](video-playback-v05.png)。

发现并修正了两个问题：Lite 曾给出超出片长的时间戳，现在校验并最多重试一次；对话曾继承旧问题的日期条件，导致日期未知的样片被过滤，现在明确以当前问题确定查询范围，不能用旧文字替代本轮检索。

最后一次从原生 App 发问（运行 `run-F4C0F781-A18A-4FCE-8904-8EE2AEE566DE`）确实重新检索并返回 A 的第 5 秒播放入口，但 Lite 描述混入了原片没有的“蓝衣人物、黑色物品、蓝色集装箱”。这次失败保留为 [模型稳定性记录](video-model-evaluation-v05.json)，不能因为时间点碰巧正确而算整体识别通过。App 结果名称改为“模型判断匹配 · 请核验”；解码温度设为 0 后，对 A 的一次复测恢复了黑衣人物拿长纸箱上 SUV 的基本过程，时间仍约 5 秒；单次恢复不能证明问题消失，仍需标注集复测。

**尚未完成：同一段连续原录像中“包裹放下 → 等待 → 被拿走”的完整验收。** 当前没有团队实拍的该类录像；不同样例不能拼成完整过程的效果证明。还需补拍/提供连续录像，并手工标注动作时间后测漏报、误报与定位误差。以上小样本只证明链路可用，不能证明普遍准确率。

## 模型与实现

- Lite：`doubao-seed-2-1-lite-260915`，使用当前私有配置，实际视频通过 `video_url` 上传，2 fps 采样。
- Embedding：`doubao-embedding-vision-251215`。未收到团队最终 Embedding ID，先采用已在当前账号验证可调用的视频模型联调，配置可以替换。
- Embedding API：`/embeddings/multimodal`；视频 1 fps，文本/视频分别使用检索指令，1024 维，L2 归一化。
- 每段 20 秒、重叠 5 秒；元数据包含摄像头、原录像 ID、采集开始时间（可空）、片段起止时间、源引用、原文件 SHA-256。
- SQLite 保存向量与元数据；小规模演示使用精确余弦排序，尚非大规模 ANN 服务。
- 候选前 3 段交给 Lite 观看真实视频；最多同时复核 2 段。视频输入并不意味着逐帧理解，短动作仍可能被采样遗漏。
- 模型输出经过结构、动作顺序和时间边界校验。只有直接可见且确认匹配才给事件时间；推断或遮挡保留不确定。此校验仍依赖模型对可见性的判断，不保证杜绝幻觉。
- 片段时间转换为原片时间后传给 App，跨片段重叠的同一动作去重。事件时间是模型估计；精确 seek 并不等于模型时间准确。
- Embedding 模型/索引策略变化后旧索引不参与查询，录像库提示重建。
- `GET/HEAD /api/recordings/{id}/video` 支持 Range/206；保留原文件，生成无音轨 H.264 播放副本和检索片段。当前只做视觉验证。
- 当前导入上限 150 MB、0.5–600 秒；视频处理依赖 PATH 中的 FFmpeg/ffprobe。失败、取消及服务重启不会发布半成品索引。

## 运行与验收

沿用 README 中服务端启动方式，在工程外的私有环境文件配置：

```dotenv
EG_MODEL_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
EG_MODEL_ID=doubao-seed-2-1-lite-260915
EG_MODEL_API_KEY=自己的密钥
EG_MODEL_VISION=1
EG_EMBED_MODEL_ID=doubao-embedding-vision-251215
```

Embedding 默认复用模型 Base URL 和 Key；可用 `EG_EMBED_BASE_URL`、`EG_EMBED_API_KEY` 独立指定。视频理解可用 `EG_VIDEO_BASE_URL`、`EG_VIDEO_MODEL_ID`、`EG_VIDEO_API_KEY` 单独配置。媒体默认在数据库同级 `recordings/`，可用 `EG_VIDEO_ROOT` 指定。

从 `Cloud` 目录 CLI 导入（日期未知就不填写 `--recorded-at`）：

```bash
EG_ENV_FILE=/私有路径/evidenceguard.env EG_DATABASE=/私有路径/app.sqlite3 \
PYTHONPATH=server .venv/bin/python -m evidenceguard.video.ingest /录像路径/parcel.mp4 \
  --camera-id cam-a --title '门口连续录像' \
  --inspect-query '描述包裹放下和被拿走的动作顺序及视频内时间'
```

App：AI → 历史回顾 → 查录像 → 编辑问题 → 发送 → 点击“播放原片”。采集日期未知时问“包裹什么时候被拿走”，不要问“今天几点”；明确按日期查询会排除未知日期录像。

本轮验证：53 项服务端测试通过，Xcode iPhone Simulator 编译通过。包括真实视频请求格式、无效时间重试、遮挡降级、模型变更索引隔离、摄像头/日期范围、片段到原片偏移、失败不产生确定证据、Range 播放、历史工具不调用摄像头。模型实测另行调用真实 API，不包含在单元测试中。

## Harness 与摄像头 SDK

视频检索已经进入同一套参考 MiiMiao 的 Runtime/Tool Registry/Provider/运行事件；历史任务的工具白名单增加 `search_recordings`。已入库视频查询和实时守护可并行，查询不连接摄像头，不切换实时任务。

T8171/T8214 保留已有 Adapter 和 `OfficialSDKBridge`。新增历史录像 `list_recordings` / `export_recording` 接口合同及带设备/通道/采集时间的 `StoredRecordingRef`，目前仅预留，不假设官方 SDK 的函数名或能力。SDK 获取录像属于独立导入流程，若触发设备 I/O，必须走 CameraService 的占用与超时边界；导入完成后的检索才是可并行的只读分析。

正式 SDK、两台实机、持续视频接入、通用实时视觉执行器、鉴权与公网部署仍待接入。本版服务继续只监听本机；摄像头实时任务约束保持每台一项。

## 参考与素材

- [火山方舟视频理解接口](https://docs.volcengine.com/docs/ark/chat-api?lang=zh&redirect=1)
- [火山方舟多模态向量化接口](https://docs.volcengine.com/docs/ark/vectorization?lang=zh&redirect=1)
- [OpenViking](https://github.com/volcengine/OpenViking)：检索组织参考，没有复制其代码。
- [Latch-Video-Package-Theft 公开数据集](https://huggingface.co/datasets/DiricziZsolt/Latch-Video-Package-Theft)：本次取其 t4/d1/o1 视频做本地测试。未见明确数据卡许可；原始视频保留在本机测试目录，不随工程交付。素材不是两款目标摄像头实测录像，未知原始日历时间。
