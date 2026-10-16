# 比赛云端 Dashboard 与快捷连接

2026-10-15。入口：**http://47.131.21.137/dashboard**。按比赛要求免登录、只读。环境下拉可选择手机演示、团队联调和 Apple 审核；原有 App API、媒体与设备接口继续使用各自的鉴权。

## Windows 一条命令连接

在本仓库根目录的 PowerShell 执行：

```powershell
.\scripts\cloud_session.ps1
```

打开 AWS Session Manager 交互式终端，不需要 SSH 私钥、服务器密码或每次打开 AWS 控制台。退出输入 `exit`。另有：

```powershell
.\scripts\cloud_session.ps1 -Action status
.\scripts\cloud_session.ps1 -Action login
.\scripts\cloud_session.ps1 -Action port-forward -LocalPort 8795
# 端口转发保持运行时访问 http://127.0.0.1:8795/dashboard
```

本机已安装并验证 AWS CLI 2.38.1 和 Session Manager Plugin 1.2.896.0。命名 profile 为 `evidenceguard-prod15`，使用 AWS 管理的临时凭证，不创建永久 Access Key；登录过期后执行 `-Action login` 完成正常浏览器登录，再回终端连接。不会修改 IAM 或安全组。

新电脑按 [AWS CLI 安装说明](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) 和 [Session Manager 插件说明](https://docs.aws.amazon.com/systems-manager/latest/userguide/install-plugin-windows.html) 安装。有效期和 IAM 条件见 [CLI 临时登录说明](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sign-in.html)；脚本不授予权限。Mac/Linux 可用 `bash scripts/cloud_session.sh connect YOUR_PROFILE`。

维护脚本可直接经 SSM 执行：

```powershell
python scripts/cloud_command.py --command 'systemctl is-active evidenceguard-demo'
python scripts/cloud_command.py --file Cloud/data/deploy/check.sh
# 连接断开或输出解码失败时只查询既有命令，不盲目重复部署：
python scripts/cloud_command.py --resume COMMAND_UUID
```

脚本固定核对账号、区域、EC2。Run Command 按已有权限执行。不要将密码、模型 Key 或整份环境文件写进命令、输出或仓库。

## 页面与采集口径

| 页面 | 实际来源与口径 |
| --- | --- |
| 运行总览 / Agent 与模型 | 真实模型 HTTP 尝试、成功状态、耗时、供应商 Usage；没有 Usage 显示未知 |
| 对话与 Trace | 任务开始、上下文准备、模型请求、工具执行、再次判断与结束回执；可进入模型和提示词详情 |
| 提示词与上下文 | 进程实际加载的固定系统提示词、工具 Schema、每次请求的角色和参数快照 |
| 设备、Skill、任务、证据 | 业务数据库只读元数据快照，不回放或执行旧任务 |
| 服务器资源 | CPU、内存、磁盘、网络速率；三套后端 PID、状态、进程 CPU、常驻内存、重启次数 |
| 部署代码核对 | 当前磁盘 Python SHA-256、进程启动指纹、指定 Git 提交的文件哈希，列出新增、缺失、变化 |
| 数据与版本 | 导出筛选记录及关联提示词；离线导入只进入浏览器，点击刷新云端数据恢复实时视图 |

采样和浏览器刷新均约 5 秒，快照超过 20 秒或连接失败会提示过期。CPU 首个区间不虚构速率；主机 CPU 的 100% 是所有逻辑 CPU，进程的 100% 是一个逻辑 CPU。内存为 `MemTotal - MemAvailable`。最近 90 个资源采样点在采集器内存中，重启后重新累计，不是长期时序数据库。

Agent 不一定调用工具；缺失回执不等于成功。Trace 展示执行事实、工具选择、耗时、状态和结果摘要，不展示模型内部推理。`reasoning_tokens` 只是供应商用量计数。主动任务存在对应回执时也显示 `proactive_started/finished`。

正文采集由部署参数 `--capture-content` 显式开启，对应 `EG_DASHBOARD_CAPTURE_CONTENT=1`。新记录可以查看完整的脱敏系统/用户/工具消息、请求参数和工具 Schema、模型原始响应、工具参数与结果，以及运行时真正返回 App 的最终回复。模型结果与运行时回退回复分别呈现，不能互相冒充。每次 HTTP 请求与提示词通过 `promptId` 关联；第二轮消息保留 `tool_call_id`。

记录详情提供分区正文和原始 JSON；Trace 的“查看最终回复”直接定位 `agent.result`。正文可随 JSON 导出/离线导入保留。未开启时仍使用元数据模式；历史记录无法恢复正文，页面明确标注。不是把已有的业务对话库整库公开。

密钥字段、当前进程实际凭证值、Bearer/Basic/JWT、私钥、Cookie、签名地址和媒体二进制在写入追踪库前过滤，采集器及浏览器再次过滤；模型内部推理不展示，`reasoning_tokens` 用量计数保留。模型输入输出是脱敏快照，不承诺与网络原始字节一致。每次捕获正文预算 512,000 字符、单字符串 256,000 字符、单集合 2,000 项，超过时标注截断；不会把截断记录标为完整。全文模式队列限制为 64 条，写满仍丢弃埋点而不阻塞业务。没有编辑提示词、执行工具、调用模型、改任务或删除数据的公开接口。

## 部署结构与兼容

```text
现有 Agent / 工具 / 模型调用
 → 增量观察器 eg_dashboard.bootstrap
 → 每环境独立 observability.sqlite3
 → 只读采集器 + /proc + systemd + 源码哈希
 → 脱敏快照 → 非特权 HTTP 服务 → nginx /dashboard
```

以下是监控初次接入时的目录；demo 后续切换为独立 release。当前维护须以 `systemctl show evidenceguard-demo -p ExecStart -p DropInPaths` 为准，并让 collector 的 demo source 与实际加载目录对应。后续变更与逐文件核对见 [demo 联调记录](DEMO-TOOLCHAIN-DEPLOYMENT.md)。

| 环境 | 原服务 / 内部端口 | 初始业务源码 | Python 环境 |
| --- | --- | --- | --- |
| team | evidenceguard / 8790 | /opt/evidenceguard/Cloud/server | /opt/evidenceguard/venv |
| demo | evidenceguard-demo / 8792 | /opt/evidenceguard-demo/Cloud/server | /opt/evidenceguard-demo/venv-build10 |
| review | evidenceguard-review / 8791 | 同 team | 同 team |

原服务增加 `40-dashboard-observer.conf` systemd drop-in，入口改为加载原应用的 `eg_dashboard.bootstrap:app`，保留原工作目录、venv、端口、环境文件、业务权限和沙箱。追踪写入各自 `/var/lib/<服务>/observability.sqlite3`。新版使用已有 `evidenceguard.ops`；旧版用打包时复制的同一实现作为兼容库，不维护两份 recorder 源码。

激活时解析 systemd 实际 `ExecStart` 并验证项目目录、端口和绑定地址，保留当前 release 的 `--app-dir`、Python 环境及其余参数；不把 demo 回退到表格中的旧默认路径。兼容测试后再次检查配置，发现并发部署变更即停止。本轮部署前读取到 demo 的业务目录为 `/opt/evidenceguard-demo/releases/briefings-20261015/Cloud/server`。

`evidenceguard-dashboard-collector` 在服务器内读取三套隔离数据库和系统资源，写入 `/var/lib/evidenceguard-dashboard/`。采集器需要 root 只读访问这些目录，但不监听网络，只允许 Unix 地址族。

`evidenceguard-dashboard` 使用单独无登录 OS 用户，监听 `127.0.0.1:8795`，只读取脱敏快照；systemd 显式屏蔽业务数据、环境文件和业务源码目录。公开路由只接受 GET/HEAD，其他方法 405，没有任意代理或命令执行入口。

```text
GET/HEAD /dashboard
GET/HEAD /dashboard/api/info
GET/HEAD /dashboard/api/snapshot?environment=demo|team|review
GET/HEAD /dashboard/api/server
GET/HEAD /dashboard/assets/<构建资源>
```

业务快照每表最多 60 行，追踪最多 3,000 条、快照预算 6 MB，截断在 coverage 声明。recorder 默认保留 20,000 条，元数据模式队列最多 2,048 条、全文模式 64 条，写满/失败不阻塞业务。历史模型请求不从业务数据补造。公开快照未导出 recorder 内存丢弃计数，界面显示未知。数据源 `local` 在云端表示服务器本地采集。

代码核对覆盖 Python 文件，不覆盖 SDK 二进制、权重、配置秘密或运行中字节码。启动指纹与磁盘相同不能证明某个 Git commit 整体已部署。三套版本号都是 0.9.0，实际代码不同。本轮业务核对基准为 `98dd0b1b9b52359cae08a3c9383aa27f18cccb47`；手机演示首次发现 21 个文件差异，包含尚未部署的 `hardware_tools`。本轮没有覆盖部署的业务源码。

## 构建、部署、回滚

```powershell
npm run build --prefix Web -- --base /dashboard/
python -m unittest discover -s Cloud/dashboard/tests -v
python Cloud/dashboard/build_release.py
python Cloud/dashboard/upload_release.py Cloud/data/deploy/dashboard.tar.gz
```

打包只包含 Dashboard/观察器、Web 产物、测试和仓库文件哈希，不包含 `.env`、AWS 凭证、官方 SDK、业务数据库或服务器源码副本。上传分块和最终包核对 SHA-256，按内容哈希创建 release；上传本身不启动服务。将输出中的实际 release 路径用于：

```powershell
python scripts/cloud_command.py --command 'python3 /opt/evidenceguard-dashboard/releases/RELEASE/activate.py --release /opt/evidenceguard-dashboard/releases/RELEASE --capture-content' --timeout 180
```

激活先用临时数据库对两套实际代码做兼容测试，再备份配置、逐套重启并核验健康状态及 API 401；随后启动采集器和公开服务、校验 nginx。失败自动回滚，备份留在 `/var/backups/evidenceguard-dashboard/<时间>/manifest.json`。主动回滚使用对应的精确目录：

```text
python3 /opt/evidenceguard-dashboard/releases/RELEASE/activate.py --rollback /var/backups/evidenceguard-dashboard/TIMESTAMP
```

回滚恢复服务和代理配置，保留追踪数据、release 和服务用户供排查。部署仍有逐套服务重启的短暂中断；进行中的 Agent 或视频索引按原应用逻辑恢复。

## 2026-10-15 验证

- 本机 Git 连通性完整性检查通过；工作区创建时的 Git for Windows 崩溃未损坏仓库，后续 fetch / fast-forward 正常。
- Web TypeScript / Vite 构建及 11 项协议/数据检查通过；最新 dongrunze 的 58 项追踪、取流、硬件工具、鉴权和 Agent 后端回归通过。
- 5 项新增 Dashboard 测试通过：公开只读路由、越界/写入拒绝、过期/损坏快照、再次脱敏、只读 SQLite、源码差异和缺失数据。
- 同一兼容脚本在本地最新版、服务器 team 旧版、demo 新版通过：模拟 transport 验证模型→工具→模型、提示词关联、工具带 name 参数、未授权工具拒绝、API 鉴权和摄像头列表。不启动后台 worker，不使用生产数据或硬件。
- 真实 demo Trace：`dashboard-smoke-70fe44dac2014861b65b2404fed2dad1`；team Trace：`dashboard-smoke-686bc87a5cdd481592ba9386b18b3606`。均 completed，各 2 次 `doubao-seed-2-1-lite-260915` HTTP 200、2 份提示词、2 次 Usage、27 条关联记录；工具为 `list_camera_capabilities` 和 `list_tasks`，可在页面搜索。
- 真实测试仅创建标记测试会话，没有取图、云台、声音、通知或其他硬件动作。`smoke_live.py` 使用真实模型额度，只供显式一次验证，不能循环当健康检查。
- 本轮未运行 iOS Simulator 或真机 SDK；摄像头协议回归不能代替实际播放、双向音频和弱网验收。Mac 交接见 [IOS-MAC-VERIFICATION.md](IOS-MAC-VERIFICATION.md)。

## 最终部署回执

- 活跃 release：`/opt/evidenceguard-dashboard/releases/f212ce8abc27d477`；发布包 SHA-256：`f212ce8abc27d4774f2dd62944b905a7da7728109ce9eb3c2d34a54edd0ff738`。源码实现提交 `a7ef5bf`。
- 对应回滚目录：`/var/backups/evidenceguard-dashboard/20261015T005440494935Z`。
- 最终版本再次完成真实模型循环：demo `dashboard-smoke-cf262c67dfcf4bac9cd49a9712114acd`，team `dashboard-smoke-78d17025a8d9479583456ad8a0974ec1`。每轮都是 2 次模型 HTTP 200、2 个只读工具、2 份提示词/Usage、27 条关联记录。
- 公网无登录 GET/HEAD `/dashboard` 200；写入 405；非法环境 422；不存在的管理路由 404。三套快照均连接、未过期、启动指纹与当前磁盘一致。三套原 HTTPS `/api/health` 200、未授权 `/api/bootstrap` 401。可重复执行 `python Cloud/dashboard/verify_public.py`，不调用模型。
- 仓库差异：demo 21 个 Python 文件；team/review 各 34 个，详情见页面。这里的“进程与启动指纹一致”与“仓库代码一致”是两个独立判断。
- 浏览器检查了实际页面、环境切换、模型→提示词关联、持续自动刷新、390px 移动布局；页面无横向溢出。实际导出的 75 条记录 JSON 通过后端 schema 校验并包含服务器采样信息。
