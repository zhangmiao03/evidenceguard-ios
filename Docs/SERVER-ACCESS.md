# 服务器 SSH 与团队协作

2026-10-13 已通过现有 SSH 连接核实。GitHub 保存后端源码和操作说明，登录凭证保存在仓库外。

## 当前连接方式

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

## 新成员接入

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

## 现场换网络：团队管理优先使用 Session Manager

上面的来源公网 IP 是成员笔记本所在网络的出口地址，用来限制 SSH 22 端口。去现场、切手机热点或换 VPN 后，它可能变化；需要更新的是 SSH 来源规则和相关管理连接条件，不需要因为笔记本换网络就重新部署后端或改手机 App 地址。给服务器换域名也不能解决客户端来源 IP 改变的问题。

团队日常管理建议改用 AWS Systems Manager Session Manager。它通过成员的 AWS 身份和 IAM 权限访问指定实例，不依赖 SSH 入站端口或固定客户端 IP；可使用浏览器终端，也可使用 AWS CLI。手机 App 继续通过 HTTPS 访问 demo 服务，这两条通路分别配置。

2026-10-13 只读检查结果：本机 `snap.amazon-ssm-agent.amazon-ssm-agent.service` 正在运行；EC2 元数据没有返回已挂载的 IAM instance profile（404）。这不证明账号层面的 Default Host Management Configuration 状态，尚未确认该实例在 Systems Manager 中在线或成功建立会话。

切换前需要完成：

1. 核对 AWS 账号的管理权限，在已有账号级管理配置或此实例专用 IAM role 中提供所需 SSM 权限；实例方式可参考 `AmazonSSMManagedInstanceCore`。这是实例服务权限，不能代替成员的登录授权。
2. 管理员确认成员访问范围，再给成员独立 AWS 身份授予这台实例的会话权限；Session Manager 的默认 Linux 会话可能拥有管理权限，需按职责配置 Run As / OS 权限。
3. 验证实例在 Systems Manager 中在线，并由已授权成员在日常 Wi-Fi 与手机热点分别开启会话。需要 VS Code Remote SSH 时，再单独验证 AWS CLI / Session Manager 插件的 SSH 隧道配置；浏览器终端不是自动可用的 VS Code SSH 配置。
4. 新通路验证通过后再处理旧 SSH 来源规则，避免失去现有管理入口。当前未更改 IAM、未新增成员权限、未关闭已有 SSH 通路。

因此，当前 SSH 密钥方案仍是已验证的现有入口；Session Manager 是准备切换的团队方案，不应在未配置及验收前告诉成员已经可用。

参考：[Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html)、[实例权限](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-getting-started-instance-profile.html)、[前置条件与默认会话账号](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-prerequisites.html)。

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
