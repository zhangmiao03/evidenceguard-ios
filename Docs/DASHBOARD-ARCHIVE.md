# 全量图片台账、历史回复和 iOS 显示校验

2026-10-17。对应问题和原始计数见 [修复前核查](IMAGE-STORAGE-AND-APP-REPLY-AUDIT.md)。核查快照不是当前实时统计。

部署、真实后端任务与校验结果见 [2026-10-17 发布验收](verification/dashboard-archive-2026-10-17.md)。

## 数据路径

手机 SDK 取样 → 业务 `media` BLOB 事务保存 → 独立只读采集器 → 脱敏分页台账与预览缓存 → 匿名 Dashboard。

业务 `runs.text` → 脱敏历史回复台账；真实执行记录 → `critical_records` → 逐步查看。两条路径独立，因此旧回复能够展示，而旧提示词缺失仍显示“未保留或当时未采集”。不会生成伪造的 `agent.result` 历史。

采集器使用只读事务访问业务数据库；HTTP 进程仅能读取 `/var/lib/evidenceguard-dashboard` 的投影，无法访问应用数据库、配置或执行硬件命令。台账是全量记录索引，不受原先每表 120 条 / 快照 3,000 条限制。当前业务表被明确删除的记录，下次投影也会移除；本功能不是业务备份。

## 接口与计数

| 接口 | 用途 |
|---|---|
| GET `/dashboard/api/archive/images` | 全量存图元数据、来源、取样时间、内容摘要、预览状态、仍保留的模型输入关联 |
| GET `/dashboard/api/archive/replies` | 业务最终回复、采集边界、App 显示回执、可读取步骤数量 |
| GET `/dashboard/api/archive/{images或replies}/export` | 当前筛选范围的全部 JSONL 记录，不只是当前页 |
| GET `/dashboard/api/archive-trace/{runId}` | 分页读取真实保留的模型、提示词、工具和最终结果 |
| POST `/api/ops/display-receipts` | 原 App 鉴权下的摘要回执；不属于匿名 Dashboard 写接口 |

两类台账参数：`environment=demo|team|review`、`limit=1..50`、`cursor`、`query`、`platform`、`source`、`device`、`since`。游标按时间和 ID 双键排序，处理同一时间戳多条记录；环境和筛选改变时前端重置游标。全库指标和筛选后的记录数分别标注。列表每 10 秒读取，显示采样时间和过期状态。

图片记录数以 `media.id` 为粒度，图片去重按实际字节 SHA-256。来源为官方事件、iOS 实时取样、合成测试等；不把合成图计作实拍。模型输入关联只能使用相同摘要，不用相近时间猜测。没有关联表示当前未保留该关联，不代表从未分析过。

匿名预览总预算仍是每环境 160 MB，磁盘副本缓存 256 MB；移除旧 160 项数量上限并修复去重、当轮引用保护。达到预算的原图仍有台账并明确显示预览不可用。业务原图独立存储，缓存不删除业务 BLOB。失败请求、从未上传的手机预览帧不承诺已存图。

## 正文与隐私

回查正文需要 `--capture-content` 和可读的配置脱敏源。采集器读取指定 `cloud.env` 与已验证运行进程的有效密钥，仅在内存用于再次脱敏；缺少源时不发布回查正文。网页不返回配置内容、密钥、外部签名 URL 或源路径。

`video_query_images` 不进入图库，带 `referenceImageId` 的任务只显示状态，正文不公开。原有私有检索观察边界继续生效。正文和 Trace 仍有明确文本大小限制，截断会标记。App 与后端正文摘要在原始文本上计算，公开显示的是脱敏文本，不要对公开脱敏文本重新计算后误报不一致。

## 关键追踪保留

沿用原 Recorder 的单后台写线程和有界队列，新建同一追踪库内的 `critical_records`。一般诊断仍保留 20,000 条；关键记录默认 10,000 条 / 128 MB，可通过 `EG_OPS_CRITICAL_RECORDS`、`EG_OPS_CRITICAL_BYTES` 调整有限范围。

优先保留 model/prompt、agent/tool/codex/context/model 事件、成功/失败取图回执和向量查询。首次启用只迁移当前追踪库中尚存的这些记录。超额按最旧活跃时间的任务整组删除，避免只随机删除中间一条；超大单任务也可能淘汰。诊断仍是尽力采集，队列满、磁盘异常、过期不能宣称全链路完整；页面采用“目前保留步骤”措辞。

## iOS 校验语义与 Mac 验收

回执包含 `runId`、`backendTextHash`、`displayTextHash`、`presentationVersion`、`appVersion`、`platform`、`status`，禁止额外正文等字段。接口保留团队访问校验及安装标识要求；只作为客户端自报诊断，不作为权限依据。

`backendTextHash` 是 App 收到的 `run.text` 原始 UTF-8 字节摘要。`displayTextHash` 是实际交给 SwiftUI `Text` 的 AttributedString 字符序列摘要。页面插入且任务结束时上报，状态或正文发生变化时重新上报；进行中的占位文字不会抢占最终回执。

Dashboard 将第一项与业务库最终正文摘要比较，显示一致/不一致；第二项作为显示转换记录，不能误称与原文摘要必须相等，更不能作为独立真机截图证明。旧客户端没有新字段时显示“旧版回执，缺少文字校验”，不判为通过。传输是有界、尽力的独立诊断通道；离线或队列满可能没有回执，不能把缺回执等同 App 未显示。

Mac 拉取 `dongrunze` 后执行 `bash scripts/test_ios_compatibility.sh`。新增哈希、Markdown 展示转换、可选回执 404 不影响原取流的测试；本机 Windows 不能运行 SwiftUI/Xcode 验收。安装新版 App 后，运行一条真实助手任务，核对后台正文一致、转换版本及 build，并人工核对屏幕；不能用服务端伪造 iOS 回执替代。

## 发布与回滚

按 `Cloud/dashboard/build_release.py`、`upload_release.py` 和 `activate.py --capture-content` 部署独立观察器，保留三环境各自业务源码、参数和原鉴权。激活前针对当前实际代码运行隔离兼容测试，含新摘要接口的 401 / 422 / 成功回执。服务逐套重启并健康检查，失败恢复精确配置备份。

本地验证包含存图超过旧上限的分页、同时间戳排序、完整导出、私有数据和配置密钥过滤、历史缺步骤、回执不一致、一般轮询淘汰不影响关键记录，以及原 App 取流、权限和 v2 检索回归。部署后记录实际计数、公开图片字节匹配、真实 Agent 任务及回滚目录，另附发布回执。
