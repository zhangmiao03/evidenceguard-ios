# 服务器、GitHub 与本地同步（2026-10-17）

同步基线：本地与 main 原为 b321730；新功能分支先核对 9937792，工作期间再纳入 d09a111。PR #5 已合并为 ec1cefb；被测整合源码 82c4e79 与合并提交的文件树完全相同。

## 整合内容

保留新分支的 iOS 视频检索与事件录像导入、硬件工具 v0.3、Seed Lite 首尾图分析、DepthART/DIS、单步视觉控制、逐次守护诊断和 Dashboard 新页面。修复两个合并回退：Web 聊天恢复自然语言动作、隐藏内部载荷与代码；Web 早安/晚间报告恢复独立开关及时间，同时兼容只识别单次报告的旧服务器。保留新增的自动记忆设置与相关测试。

前次实际手机后端为 tools-e4725de3d0d287d8，业务源码与 9937792 完全一致。d09a111 新增守护诊断，需将后端与观察器一起更新。同步仅涉及 demo 和独立 Dashboard；team / review 的业务代码、凭据、进程应保持不变。

## 验证

- 整合后本地后端 495 项通过，包括实际合成像素的 DepthART/DIS 检查；没有用合成资料宣称真机验收。
- Dashboard Python 41 项、发布工具 31 项、Web 单元 26 项通过；生产构建通过。
- Chrome 产品与工作区 29 项通过，1 项需本地官方网页 SDK 的用例跳过；演示面板相关 6 项通过。恢复的回归覆盖执行状态、代码隐藏、用户原话保留、独立报告设置及旧服务兼容。
- 移动端契约/状态检查与 iOS Simulator Debug 编译通过。此次未做真机 SDK、摄像头动作或 APNs 验收。
- Linux 候选后端 494 项通过，1 项由于部署目录不包含仓库 LFS 权重路径而跳过。线上使用已验证的独立权重目录，发布前另做权重及依赖检查。
- GitHub CI 单独以其运行状态为准；本地通过不代表所有远程任务已完成。

## 部署状态

同步完成。执行切换前，发现并行发布已将 d09a111 同一份后端部署为 `/opt/evidenceguard-demo/releases/tools-1ba936f71aaa3edf/Cloud/server`。漂移检查拒绝重复覆盖，重新核对这份运行代码的 136 个文件与合并后本地代码完全一致，因此保留该后端。

本次仅切换 demo 静态产品页至 `/opt/evidenceguard-demo/releases/tools-sync-82c4e79/web`，统一 Dashboard 服务、采集器和静态资源至 `/opt/evidenceguard-dashboard/releases/sync-82c4e79`。只重启 demo / Dashboard / collector；team、review 进程及其参数保持原值。保留原官方网页 SDK 和旧静态资源，避免已打开的页面丢失延迟加载文件。

同步后的三个业务服务健康 200、无凭据 bootstrap 401；现有手机身份 bootstrap 200，登记摄像头 2 台、聊天模型 ready、embedding ready、检索版本 2。公网产品及 Dashboard 均 200。所有原业务表主键均保留，三个 SQLite quick_check 均 ok；私有配置文件哈希不变，聊天密钥与用户最新提供的密钥一致。没有更换 embedding 密钥、启停用户守护、发送通知或执行硬件操作。

恢复配置在服务器 `/var/backups/evidenceguard-sync/20261017T002024Z`，旧版本目录仍保留。完整私有运行清单、源文件校验、测试日志、数据 ID 清单及 Git 恢复包保留在当前接续工作区的 `work/private/sync-20261017/`，不进入公开仓库。没有新增 TestFlight 上传或分发；源码同步不等于手机已装新版客户端。
