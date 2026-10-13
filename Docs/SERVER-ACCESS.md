# 服务器访问与团队协作

2026-10-13 已配置并实际验证 AWS Systems Manager Session Manager（SSM）。团队管理优先使用 SSM，现有 SSH 保留为备用入口。GitHub 保存后端源码和操作说明，登录凭证保存在仓库外。

## 换网络后的日常连接：Session Manager

在已登录且具有该实例 SSM 权限的 AWS 控制台中：

1. 选择 **美国西部（俄勒冈）/ us-west-2**。
2. 打开 EC2 → 实例，选择 `evidenceguard-api` / `i-06744490347d73778`。
3. 点击「连接」→「SSM 会话管理器」→「连接」。
4. 终端使用完输入 `exit` 结束自己的会话。

这条管理通路不依赖笔记本的固定公网 IP 或 SSH 22 入站规则。去深圳、切手机热点或换 Wi-Fi 不需要因此重新部署后端或修改 App 地址；新网络仍需能正常访问 AWS 控制台及 SSM 服务。手机 App 的 HTTPS 请求与管理员登录服务器是两条不同通路。

### 已完成的配置和验证

| 项目 | 已核实的状态 |
| --- | --- |
| AWS 账号 | `083151142234` |
| EC2 实例 | `i-06744490347d73778`，`us-west-2` |
| 实例 IAM role | `EvidenceGuardSSMInstanceRole`，信任主体为 `ec2.amazonaws.com` |
| 唯一附加的托管策略 | AWS 官方 `AmazonSSMManagedInstanceCore` |
| Instance profile | `EvidenceGuardSSMInstanceProfile`，关联状态 `associated` |
| SSM agent | `3.3.4793.0`，诊断中的实例身份、凭证、网络与服务检查通过 |
| 控制台连接状态 | 在线 / 已连接 |
| 实际终端验证 | 已通过浏览器 SSM 会话执行命令；登录用户为 `ssm-user` |
| 后端服务 | `evidenceguard-demo`、`evidenceguard`、`evidenceguard-review` 均为 `active` |
| 演示服务健康检查 | 会话内 `http://127.0.0.1:8792/api/health` 返回 `{"status":"ok"}` |

验证完成后已用 `exit` 结束测试会话。本次只重启了 SSM agent，没有重启或重新部署三个后端服务，没有修改安全组、现有 SSH 或新增成员授权。默认 SSM 会话具备 sudo 管理能力，因此只有被明确授权的管理身份才能使用。

尚未进行现场网络或 Wi-Fi / 热点切换实测；尚未为队友创建独立 AWS 身份，也未验证 VS Code Remote SSH 经 SSM 隧道连接。不要把浏览器终端已连通理解为这些事项均已完成。

### 本机命令行入口

仓库提供 [cloud_session.sh](../scripts/cloud_session.sh)，用于检查目标账号与实例状态，然后按需打开会话：

```bash
bash scripts/cloud_session.sh check YOUR_AWS_PROFILE
bash scripts/cloud_session.sh connect YOUR_AWS_PROFILE
```

需要先安装 AWS CLI v2、官方 Session Manager 插件，并配置本人已获授权的 AWS 登录；不传 profile 时使用 CLI 的默认身份。浏览器登录不会自动配置本地 CLI。2026-10-13 这台开发 Mac 尚未配置该 CLI 入口；脚本已完成语法和四条模拟 CLI 分支验证，真实服务器会话通过浏览器验收。

脚本不创建凭证、不修改 IAM 或安全组。`check` 显示 connected 仅表示 SSM 状态正常，成功打开并执行命令才算会话验收。

[ssm-instance-role.json](../Cloud/infra/ssm-instance-role.json) 保存角色与 profile 的 CloudFormation 参考定义，用于复核或受控重建。本次实际资源通过 AWS CLI 创建，**不由 CloudFormation stack 管理**；当前账号已有同名资源，不可直接部署此模板，否则会名称冲突。模板也不会自动绑定实例或授予成员权限。

### 队友接入

给队友独立 AWS 身份，再按职责授权访问指定实例。拥有 GitHub 仓库权限不等于拥有服务器权限；实例上的 SSM role 也不能代替成员身份权限。避免共享管理员 AWS 登录或 SSH 私钥。

只读日志与部署管理应分别定义权限；需要限制操作系统权限时另行配置 Session Manager Run As 和 Linux 账号。授予成员权限后，分别验证其本人会话与热点连接，再决定是否收紧旧 SSH 入口。

参考：[Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html)、[实例权限](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-getting-started-instance-profile.html)、[前置条件与默认会话账号](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-prerequisites.html)。

## 保留的 SSH 备用入口

| 项目 | 当前值 |
| --- | --- |
| 云平台 / 区域 | AWS EC2 / us-west-2 |
| 公网 IP | `34.218.51.85` |
| SSH 端口 | `22` |
| 现有管理员登录账号 | `ubuntu` |
| 认证 | SSH 公钥认证，客户端持有对应私钥 |
| 密码登录 | `PasswordAuthentication no` |
| root | 密码处于锁定状态；当前管理连接使用 ubuntu，按需 sudo |

AWS 控制台的 IAM 用户密码、模型 API Key、App 服务访问令牌均不是 SSH 登录密码。当前没有可提供给成员的 root 登录密码。

管理员已有私钥时，使用自己电脑上的真实路径：

```bash
chmod 600 /path/to/owner-key.pem
ssh -i /path/to/owner-key.pem ubuntu@34.218.51.85
```

这是现有管理员的连接方式，不表示新成员已获得该密钥或访问权。私钥不提交到 GitHub，也不放进群聊天。

本实例已核对的 ED25519 主机指纹：

```text
SHA256:m3m0KCupVlW7U9+bTJdPPqKF2NzyS+zC+O8urazekVs
```

首次连接时核对指纹；出现变化时先向管理员核实实例或主机密钥是否更换，不关闭主机校验。

### 需要传统 SSH 的成员

新成员在自己的电脑生成专用 SSH 密钥，私钥由本人保留。下例用于尚未存在的文件；已有该文件时不要覆盖：

```bash
ssh-keygen -t ed25519 -f ~/.ssh/evidenceguard_team
cat ~/.ssh/evidenceguard_team.pub
```

交给项目管理员的是 `.pub` 公钥和当前出口公网 IP。管理员确认访问范围后，配置独立 Linux 账号、登记公钥，并在 EC2 安全组允许该成员的实际来源 IP 访问 TCP 22。新的账号及权限尚未创建；拥有 GitHub 仓库权限不等于拥有服务器权限。

配置完成后，管理员告知实际账号名，再连接：

```bash
ssh -i ~/.ssh/evidenceguard_team YOUR_ASSIGNED_USERNAME@34.218.51.85
```

成员不用共享现有 ubuntu 管理员私钥。普通查看日志与部署修改可分别授权，sudo 范围按实际职责设置。

连接超时：先检查实例状态、成员当前出口 IP 与安全组 22 端口来源是否匹配，再检查本地网络。
`Permission denied (publickey)`：检查账号名、使用的私钥，以及该账号是否已登记对应公钥。

## 当前后端环境

三个服务运行在同一台 EC2 上，使用不同服务用户、数据库和访问令牌。

| 环境 | HTTPS 地址 | systemd 服务 | 源码 | 数据目录 |
| --- | --- | --- | --- | --- |
| 手机内部演示，TestFlight 3/4 | `https://demo.34.218.51.85.sslip.io` | `evidenceguard-demo` | `/opt/evidenceguard-demo/Cloud/server` | `/var/lib/evidenceguard-demo` |
| 原团队联调 | `https://34.218.51.85` | `evidenceguard` | `/opt/evidenceguard/Cloud/server` | `/var/lib/evidenceguard` |
| Apple 审核 | `https://review.34.218.51.85.sslip.io` | `evidenceguard-review` | 与原团队服务共用源码 | `/var/lib/evidenceguard-review` |

当前手机主线修改应部署到 demo 源码目录。原团队与 Apple 审核服务不要随手机演示更新一起替换。不要增加 Uvicorn worker 或副本；现有摄像头占用协调要求单个进程。

获得相应权限后，先查看状态和日志：

```bash
systemctl status evidenceguard-demo --no-pager
sudo journalctl -u evidenceguard-demo -n 100 --no-pager
curl --fail https://demo.34.218.51.85.sslip.io/api/health
```

健康检查可匿名访问，只证明服务进程在线。对话、设备和证据 API 仍需要服务访问令牌，模型是否可调用要另外验收。TestFlight 3/4 已自动配置内部演示连接，手机用户无需填写凭证。

环境配置在 `/etc/evidenceguard-demo/cloud.env`，只能由已授权人员或服务进程读取；文件包含服务令牌及模型配置，不粘贴进 Git、issue 或聊天。更新前备份代码、数据库和配置，验证失败应回滚。部署说明见 [Cloud 部署](CLOUD-DEPLOYMENT.md)。

官方参考：[EC2 SSH 连接条件](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/connect-to-linux-instance.html)、[EC2 公私钥机制](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-key-pairs.html)。

## 新加坡 / 香港迁移评估（尚未迁移）

2026-10-13 在当前账号读取区域状态：

| 区域 | AWS 返回状态 | 当前结论 |
| --- | --- | --- |
| 新加坡 `ap-southeast-1` | `opt-in-not-required` | 已启用，可作为迁移候选；实例创建权限、配额及容量仍需验证 |
| 香港 `ap-east-1` | `not-opted-in` | 尚未启用，需要有权限的账号管理员先启用后再评估 |

优先评估新加坡。地理距离更近不能保证实际链路更快；需要在深圳或相近用户网络比较 HTTPS、视频下载和模型调用全链路。当前 Mac 到俄勒冈 demo 健康接口的三次新连接请求均 HTTP 200，总耗时约 0.58–0.78 秒（包含 TCP/TLS）；这不是模型响应时间，也没有与新加坡同配置实例作对照。

迁移需要在目标区域部署新实例，而非修改现有实例的区域属性；可以复制 AMI / 快照或重新部署服务。两区并行验证、快照及传输可能产生费用，当前没有新建这些资源。参见 [AWS AMI 跨区域复制](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/CopyingAMIs.html)。

建议按以下顺序推进：

1. 确认赛事账号允许的区域、资源预算和新加坡实例配额，再准备目标实例与 SSM。
2. 为手机 demo 使用团队可控的固定域名，并配置可信 HTTPS。现有 `demo.34.218.51.85.sslip.io` 直接映射旧 IP，不能当作可自由改解析的团队域名；当前 EC2 公网地址也未绑定 Elastic IP。
3. 先迁移手机 demo：安全复制模型配置、服务令牌、录像及一致性 SQLite 备份，保留原团队和 Apple 审核服务。切换时同一数据集 / 摄像头只保留一个实时 Skill 与主动任务调度进程，避免两台服务器同时执行。
4. 对比新区域的健康接口、自动演示登录、真实对话、录像播放和任务执行；记录模型 API 的独立耗时。
5. 更新 iOS 内置 `EGServiceBaseURL`，上传新的 TestFlight 构建并验收。当前 3/4 构建内置旧地址；访问令牌只对同源 HTTPS 服务发送，不应放宽这条限制来迁移。
6. 验证切换和回滚后再安排旧资源退役。保留旧主机做代理可以临时兼容旧包，但用户仍经过俄勒冈，不能当作完整的延迟优化。

本次 SSM 改造不需要重发 App；区域迁移和固定域名切换是后续独立工作。
