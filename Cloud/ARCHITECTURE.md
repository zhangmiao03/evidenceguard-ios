# EvidenceGuard 技术架构

## 纵向链路

```mermaid
flowchart LR
  A[原生 SwiftUI iPhone App] -->|HTTPS JSON| B[FastAPI API]
  B --> C[Agent Runtime]
  C --> D[Tool Registry]
  D --> E[Skill Store / Events]
  B --> F[Observation Worker]
  F --> L[CameraService: 设备互斥与执行凭据]
  D --> L
  L --> G[Camera Registry]
  G --> H[fixture-lab adapter]
  G -. SDK 到手后切换 .-> I[T8171 adapter]
  G -. SDK 到手后切换 .-> J[T8214 adapter]
  H --> K[RTSP Camera Lab]
  F --> E
```

原生 iPhone App 不直接依赖摄像头厂商 API。Camera Registry 输出设备能力清单和统一 FrameRef；Worker 只处理新鲜度、设备/通道身份、视角版本和证据。这样 SDK 的 P2P、云端、HomeBase 或局域网差异被限制在适配器内。

## Skill 状态模型

- `status`：`draft / active / paused / stopped / completed`，表示任务生命周期。
- `result`：`initializing / confirmed / needs_attention / unknown`，表示最近一次可解释结果。
- `alert`：`none / open / acknowledged / resolved`，表示告警处理进度。

三者分开保存。目标离区只打开告警，不结束持续任务；重新检查先回到 `unknown`，拿到新证据后才确认恢复。

## Harness 参考

Harness 参考本地 MiiMiao v1.0 对照仓库提交 `fe43a78` 的三项结构：集中式 Tool Registry、Provider 边界、按 run 分配的 durable sequence events。这里实现的是黑客松需要的最小子集，没有复制 MiiMiao 的大型通用 Runtime。

工具包括：

- `list_camera_capabilities`
- `request_camera_snapshot`
- `draft_visual_skill`
- `list_tasks`
- `get_task_state`
- `search_recordings`（Embedding 召回、Lite 视频复核）
- `search_evidence`
- `read_stored_image`
- `request_recheck`

每次 Agent 请求持久化为 run，记录 `run_queued → run_started → model_started → tool_started → tool_completed/failed → response_completed` 等有序事件。Provider 通过配置的 OpenAI-compatible Chat Completions 接口调用当前配置的方舟 Lite。单次运行最多 8 轮，实时对话最多 3 个、历史分析最多 2 个并发，支持取消、超时、请求 ID 去重与重启中断标记。工具只能生成待确认草案，不能代替用户启用任务。历史模式的工具注册表只有 `search_evidence / read_stored_image / search_recordings`，即使模型请求其他工具也会被拒绝。

App 每个标签使用独立 NavigationStack，AI 标签直接显示对话与底部输入框；详情复用对话组件并带任务上下文。语音使用 Apple Speech 转写，用户编辑确认后才发送。

## 下一阶段替换点

1. 主办方提供 SDK 后实现两个正式 Adapter，并通过设备握手生成 capability manifest。
2. 使用真实设备记录 `capturedAt / receivedAt / clockOffsetMs / uncertaintyMs / viewRevision / calibrationRef`。
3. 将目标检测替换为通用视觉模型，同时保持 Skill/证据合同不变。
4. 把 FastAPI 和对象存储部署到公网，为 App 配置正式 API 地址与鉴权。


## v0.3 联动更新

加入按任务限定的工具上下文、实际新图请求与回执、TaskEnvelope 工作负载限流、语义状态转换 checkpoint、告警 episode 去重及独立图片持久化。具体范围、验收和剩余边界见 [v0.3 记录](../Docs/SKILL-RUNTIME-v0.3.md)。

## v0.4 摄像头占用

每台物理设备（包含其全部通道）只有一个 active Skill。SQLite `BEGIN IMMEDIATE` 使检查冲突、暂停占用任务、启用目标任务成为一次原子提交。多摄像头任务同时占用全部绑定设备。每次启用/恢复生成新的 executionEpoch；App 切换确认携带所见占用任务的 epoch，状态变化时重新确认。CameraService 使用每设备异步锁让旧命令结束后再切换，排队请求执行前与回执入库前校验 epoch。当前是单服务进程实现，不是分布式设备租约。

实时助手查看画面沿用当前守护的所有权；历史 run 只读取 SQLite 中的不可变证据及持久化图片。缓存读取不得触发设备操作，后续 SDK 的 `state / frame_bytes` 必须遵守此约束。详情见 [v0.4](../Docs/CAMERA-OWNERSHIP-v0.4.md)。

## v0.5 历史视频

VideoService 将本地原录像转为可播放副本与重叠片段，VideoStore 保存源信息、片段范围、模型签名和向量。Agent 通过 search_recordings 检索并复核候选，不触达设备层。API 支持范围播放，SwiftUI 证据卡传递原片时间给 AVPlayer。当前是 SQLite 精确余弦检索，尚非大规模视频索引。完整实现、测试结果与模型效果边界见 [v0.5](../Docs/VIDEO-HISTORY-v0.5.md)。

## v0.6 查询范围与可核验结果

App 传 HistoryFilter，Runtime 将其解析并持久化为固定 HistoryScope，由工具层强制执行；模型只能提出查询内容。VideoService 通过回调写入持久化阶段事件，历史查询仅使用当前工具回执生成摘要并关联卡片。视觉 Provider 的失败单独标记，不与遮挡混淆。回归脚本独立评测分类、定位、失败和耗时，保留人工描述审核以及缺失场景。详见 [v0.6](../Docs/VIDEO-RELIABILITY-v0.6.md)。
