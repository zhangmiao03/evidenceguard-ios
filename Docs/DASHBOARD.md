# EvidenceGuard 本地研发 Dashboard

本轮参考桌面 AIBuddy 的深色侧栏、全局筛选、概览指标、明细与追踪工作流，集成到现有 Web 工程的 `/dashboard`。不复制 AIBuddy 的家庭/儿童业务模型，不连接生产服务器，不需要 root。普通 App 路由和官方 SDK 工作区继续保留。

## 启动

仓库根目录，在已有 Python 虚拟环境中安装 `Cloud/server/requirements.txt`。Node 依赖使用锁文件。

```powershell
cd Web
npm ci
npm run build
cd ..
.venv/Scripts/python.exe scripts/run_dashboard.py
```

macOS/Linux 使用对应 Python 路径，例如 `Cloud/.venv/bin/python scripts/run_dashboard.py`。打开 `http://127.0.0.1:8790/dashboard`，点击“连接本地服务 → 读取同源本地 API”。App 在同一地址 `/`。离线导入不需要 API，也不需要官方 SDK 或模型 Key。

启动器默认隔离到 `Cloud/data/local-dashboard/`，不会隐式读取团队云端配置；仅绑定 `127.0.0.1`，单进程。`business.sqlite3` 是正常应用状态，`observability.sqlite3` 是独立追踪库，不能配置为同一文件。不要启动多个进程竞争设备会话。更换端口用 `--port 8791`。`--data-dir` 可指定一个本地开发数据目录。必要时显式用 `--env-file` 加载自己选择的本地模型配置；不要传入生产部署环境文件。

现有后端也可设置 `EG_OPS_ENABLED=1`、可选 `EG_OPS_DATABASE`，并把 `EG_WEB_ROOT` 指向构建出的 `Web/dist`。默认关闭采集。开发热更新可以同时启动 Vite（`cd Web; npm run dev`），其 `/api` 代理到本地 8790。

纯离线演示：Vite 或 `vite preview` 打开 `/dashboard`，在“数据与版本”点击“载入模拟样例”，或者导入 JSON。样例始终有“模拟”标识，首次打开不会自动填入假指标。

## 页面与数据口径

| 页面 | 当前可检查内容 |
|---|---|
| 运行总览 | 关联 trace 数、实际 HTTP 模型尝试、HTTP 成功率、完整请求 P95、已知 Token、失败记录 |
| 设备与取流 | 设备登记快照、媒体会话创建/状态/停止/过期、首帧、新帧请求与接收 |
| 对话与 Trace | 同一 trace 的客户端、Agent、模型、工具、画面记录；span/parentSpan 关联 |
| Agent 与模型 | 主对话、主动评估、图片/视频/区域核验、Embedding、官方 Demo 实际调用；配置单独标识 |
| 提示词与上下文 | 每次 HTTP 尝试的请求快照、工具 Schema、参数、角色、摘要/可选全文、脱敏快照哈希 |
| Skill 与任务 | 最近 100 个 Skill/Run 快照，执行事件与业务回执 |
| 证据与录像 | 元数据和实际采集/核验链路，不自动下载原始媒体 |
| 质量与试跑 | 试跑快照、失败/取消/不支持记录、缺失和采集边界 |
| 用量与覆盖 | 服务商返回的 Usage、回执覆盖分母、丢弃/写入失败/截断，不推算云账单 |
| 数据与版本 | 离线文件导入、筛选导出、本地追踪归档、显式模拟数据、清除页面内存 |

所有顶部指标、图表、列表使用同一筛选记录。时间窗口相对**文件/快照时间**，不是浏览器此刻时间。Trace 明细显式显示同一 ID 的完整上下文，可包含筛选外记录。表格最多展示 100 条，Trace 列表最多 80 组；指标和导出覆盖完整筛选结果，超过展示上限会提示。

模型请求按真实 HTTP 尝试计数，视频输出校验重试会产生两条调用和两份提示词。`http_ok` 不是业务成功；同一 trace 的 `*.finished`、`run_*` 和工具回执才说明校验/执行结果。P95 使用 nearest-rank、完整 HTTP 往返耗时，不是首字延迟。Usage 缺失显示未知，只合计含数值 `total_tokens` 的请求；没有单价/计费版本就不显示金额。

客户端记录含 `appVersion`（iOS 读取实际版本/构建号，Web 为源码版本）；服务端 coverage 含 `buildRevision`。本地启动器读取 Git HEAD，也可由构建系统显式设置 `EG_BUILD_REVISION`；未提交修改不等同于该提交的已发布构建。没有版本信息时显示 unknown，不推断线上正在使用的版本。

## 追踪实现和可信边界

```text
iOS / Web requestId + X-EG-Trace-ID
    → HTTP 请求 → Agent run（traceId = run.id）
      → chat / tool / camera.capture span
        → 服务端新帧 challenge（traceId / parentSpanId）
          → 客户端 capture.sampled → 服务端 frame_accepted
        → 真实主模型视觉或独立 image_review 调用
      → Agent 结束状态 → 客户端收到结果
```

- `ops.py` 使用 ContextVar 关联异步工作；多个请求并行不共享全局可变 trace。模型与截图失败不会被“调用结束”误判成已成功。
- 追踪写入独立线程和有界队列（默认 2048）。队列满、写入失败计数；不重试客户端埋点，埋点失败不阻塞业务。SQLite 留存最近 20000 条；单次快照最多 10000 条，并限制序列化体积。丢弃和淘汰计数从进程启动累计，不能当作完整历史统计。
- 客户端只可上报固定名称和元数据；服务端强制 `source=client`，不能上传模型记录、提示词或任意对象。安装标识仅用于命名空间去重，不写入导出包。客户端平台、首帧与采样属于客户端自述，无法证明硬件传感器拍摄时间。
- `sampledAt` 是客户端取样时间，`receivedAt` 是服务端接收时间，`capturedAt` 仍可能为空。跨机器时钟未经同步，不用两端墙钟差计算延迟。只有本进程单调时钟耗时可直接解释。
- 旧版 `events.run_id` 同时用于任务、Run 和截图主体。没有现有 trace 时保留 `subject:` 关联，不宣称它必然是 Agent 根请求。未采集的旧事件不伪造为新历史。
- iOS/Web 通用 API 埋点覆盖写操作，排除频繁心跳和 presence；直播另有首帧、采样、停止。官方闭源 SDK 内部 BLE、P2P、编解码、私有模型执行细节不可见，当前不声称完整覆盖这些内部调用。
- 当前 Dashboard 是单团队本地研发工具，不能代替生产多租户授权审计、推送送达证明、真机连续守护验收或评测标注系统。

## 模型与提示词

实际 HTTP 层记录模型 ID、操作类型、固定网关 hostname、HTTP 状态、允许的 provider request ID、Usage、耗时及 promptId。主模型 `OpenAICompatibleProvider`、`LiteVideoProvider` 的图片/视频/区域判断、`ArkVideoEmbedding`、服务端官方 Demo AI 代理均接入。主动 Agent 通过同一主模型记录，不把固定配置或 mock provider 计作真实模型 HTTP 调用。

默认可见首条固定 system、工具定义、调用参数；用户文字、后续 system 记忆、assistant/tool 上下文仅保留长度和 SHA-256 摘要。需要本地调试动态文本时显式启动：

```powershell
.venv/Scripts/python.exe scripts/run_dashboard.py --capture-content
```

现有服务可设置 `EG_OPS_CAPTURE_CONTENT=1` 后重启。该开关只影响新记录，不能恢复旧记录。开启后导出可能包含用户对话/记忆，请由团队决定文件接收人。二进制图片/视频、Authorization、API Key、密码、设备 SN、账号标识、签名 URL 始终过滤。快照哈希针对**脱敏后的快照**，不声称等同原始 HTTP 字节。这里可查看提示词，不提供在线编辑生产提示词的接口。

## 导入、导出和 API

包格式为 `evidenceguard.ops/v1`，纯 JSON，最多 20 MB / 10000 条。包含 `dataset`、`records`、`coverage`；每条记录有唯一 id、kind、name、at、traceId、spanId、parentSpanId、platform、source、status、durationMs 和 data。导出不包含原始媒体、SQLite 文件、环境文件或访问密钥。浏览器只解析数据，不执行 HTML/脚本，不打开导入数据中的链接。

浏览器导入只放当前页面内存；再次导入会替换当前数据集，刷新页面清空。导出采用当前筛选，并补齐选中模型调用的关联提示词，在 coverage 标明补入数量；生成新导出 ID，快照时间保留原观测时间。同一文件归档重复导入幂等；相同数据集 ID 内容不同会整包拒绝，不局部合并。导入到服务端只写独立追踪库，不能恢复或修改任务、设备、记忆。

| 方法与路径 | 用途 / 权限 |
|---|---|
| `GET /api/ops/snapshot` | 本地当前记录 + 只读资源快照；Dashboard 权限 |
| `GET /api/ops/export?dataset=<id>` | 未传 id 导出新快照；传 id 读归档；Dashboard 权限 |
| `GET /api/ops/datasets` | 列出已归档离线数据集；Dashboard 权限 |
| `POST /api/ops/import` | 原子校验并归档 JSON；Dashboard 权限 |
| `POST /api/ops/client-events` | 最多 32 条 / 32 KB，标准 App 权限 + 安装标识；关闭采集时无操作 |

Dashboard 权限：默认无团队密钥时只允许回环本机；启用了团队访问令牌，或要从非回环访问，必须配置独立 `EG_OPS_TOKEN`（至少 32 字符），请求带 `X-EG-Ops-Token`；团队鉴权仍有效，另带 `Authorization`。Ops token 不进入 iOS/Web App，也不保存到浏览器持久存储。浏览器跨源请求拒绝。不要把无鉴权本地服务通过反向代理暴露到公网。

## 测试与交付边界

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe scripts/check_repository.py
cd Web
npm test
npm run build
npx playwright test
```

新增测试覆盖并发上下文、真实调用与输出校验区分、取消、敏感信息过滤、导入幂等/冲突、客户端防伪造、独立权限、业务库不变、取帧 trace 贯通、四浏览器的离线导入→模型→提示词→Trace→筛选导出、错误输入与手机布局。iOS 在 Windows 不可编译；由仓库 macOS CI 编译模拟器并执行兼容性检查。真机 SDK、前台首帧、iOS/手机 Safari 现场时间与断网行为仍需拿设备联调，不由合成浏览器数据证明。
