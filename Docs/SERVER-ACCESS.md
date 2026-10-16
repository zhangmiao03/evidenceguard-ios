# EvidenceGuard 服务器与访问

2026-10-14：手机、团队联调和 Apple 审核服务已迁入新加坡。三套服务保留原来的独立账号、数据库、录像和访问令牌，每套只有一个应用进程。美国实例 `i-06744490347d73778` 已删除，AWS 已确认 `terminated`。旧地址不再提供服务，手机须在 TestFlight 更新到 `1.0 (5)`。

## 当前资源

| 项目 | 值 |
| --- | --- |
| AWS 账号 | `083151142234` |
| 区域 | 新加坡 `ap-southeast-1` |
| EC2 | `i-010907ed19e2cc23a`，`t3.medium` |
| 固定公网 IP | `47.131.21.137`（Elastic IP） |
| 系统盘 | 30 GB 加密 gp3，随实例删除 |
| SSM profile | `EvidenceGuardSSMInstanceProfile` |
| 管理入口 | AWS Systems Manager；SSH 仅保留既有管理员来源 |

| 环境 | HTTPS 地址 | systemd 服务 / 数据目录 |
| --- | --- | --- |
| 手机内部演示 | `https://demo.47.131.21.137.sslip.io` | `evidenceguard-demo` / `/var/lib/evidenceguard-demo` |
| 团队联调 | `https://team.47.131.21.137.sslip.io` | `evidenceguard` / `/var/lib/evidenceguard` |
| Apple 审核 | `https://review.47.131.21.137.sslip.io` | `evidenceguard-review` / `/var/lib/evidenceguard-review` |

手机原始源码在 `/opt/evidenceguard-demo/Cloud/server`，后续 demo 使用独立 release 目录，不能再把原始目录当作运行版本。维护前用 `systemctl show evidenceguard-demo -p ExecStart -p DropInPaths` 核对实际路径；10 月 15～16 日的发布与差异见 [demo 联调记录](DEMO-TOOLCHAIN-DEPLOYMENT.md)。团队和审核共用 `/opt/evidenceguard/Cloud/server`，只共用源码，不共用数据和凭证。模型密钥留在服务器的 `/etc/<服务名>/cloud.env`，不提交到 Git 或聊天。

三个 HTTPS 入口使用受信任证书，每六小时检查续期；三个证书的续期演练均已成功。地址依赖当前 Elastic IP，不能释放或更换它后仍期望旧地址有效。换笔记本 Wi-Fi 不会改变服务器地址。

## 管理连接

2026-10-16（新加坡时间）重新通过 Codex 内置浏览器授权 AWS CLI 后，AWS 查询确认实例仍为 `i-010907ed19e2cc23a`，公网 IP 仍是 **47.131.21.137**，状态 `running` / SSM `Online`；五个应用与监控服务均 `active`。更换笔记本网络不需要改服务器 IP 或开放新的 SSH 来源。SSM 按实例 ID 连接。

Windows 快捷脚本现在会读取已启用的系统 HTTP/HTTPS 代理，仅用于本次进程；不会更改系统代理或关闭证书验证。显式的 `HTTP_PROXY` / `HTTPS_PROXY` 优先；可用 `-NoSystemProxy`（PowerShell）或 `--no-system-proxy`（Python）禁止自动继承。当前机器的系统代理在 `127.0.0.1:7890`，脚本不写死这个地址。PAC/需交互认证的代理不自动解析，需要设置可用的代理环境变量。

```powershell
# 在仓库根目录执行；status 同时查询 AWS 当前公网 IP 与 SSM 状态。
.\scripts\cloud_session.ps1 -Action status
.\scripts\cloud_session.ps1

# 执行只读检查；运行失败时先看 SSM command ID，使用 --resume 查询，避免重复执行。
python scripts/cloud_command.py --command 'systemctl is-active evidenceguard-demo'

# 仅当 AWS 临时登录过期时重新授权；不需要每次打开 Web 控制台。
.\scripts\cloud_session.ps1 -Action login
```

AWS 控制台密码不作为 SSH 密码，也不存进脚本。CLI 临时凭证由 AWS CLI 管理；不要把登录缓存、验证码或密钥发送给其他会话或提交仓库。

2026-10-15：Windows 本机已用 `evidenceguard-prod15` profile 完成临时 AWS CLI 登录，并实际打开 SSM shell、执行 `whoami` 后正常退出。PowerShell 快捷入口为 `.\scripts\cloud_session.ps1`；`-Action status` 查看状态，`-Action login` 更新过期登录。比赛只读监控入口为 **http://47.131.21.137/dashboard**。部署和权限边界见 [云端 Dashboard](CLOUD-DASHBOARD.md)。

AWS 控制台选择新加坡，打开该实例的“连接 → SSM 会话管理器”。现有 SSM role 是 `EvidenceGuardSSMInstanceRole`，附加 AWS 官方 `AmazonSSMManagedInstanceCore`。它是实例身份，不会自动授予队友访问权限；本轮没有新增成员。

已授权身份也可以使用仓库脚本：

```bash
bash scripts/cloud_session.sh check YOUR_AWS_PROFILE
bash scripts/cloud_session.sh connect YOUR_AWS_PROFILE
```

需要 AWS CLI v2、本人有效的 AWS 登录；`connect` 另需官方 Session Manager 插件。脚本核对账号、区域和实例，不创建凭证或修改权限。`check` 成功不等于交互式会话已验证。

现有管理员 SSH 备用入口为 `ubuntu@47.131.21.137`，使用自己持有的管理员私钥；密钥不在仓库中。新加坡实例已核对的 ED25519 指纹：

```text
SHA256:ivo15ElurgT+IyAaURo05qYwBuXyHLSidV4cK4DQxyc
```

首次连接必须核对；指纹变化时先确认实例和主机密钥，不关闭验证。密码登录关闭，root 密码锁定。AWS 登录密码、模型 Key、App 服务令牌都不是 SSH 密码。

## 运行与切换验证

```bash
systemctl status evidenceguard-demo --no-pager
sudo journalctl -u evidenceguard-demo -n 100 --no-pager
curl --fail https://demo.47.131.21.137.sslip.io/api/health
```

健康接口只证明进程在线。迁移另验证了三环境匿名 401、独立令牌访问 200、交叉令牌 401，以及实际模型对话；手机和审核的合成录像通过媒体 Cookie 的 Range/206 和 HEAD 检查。真实摄像头、蜂窝网络和实际 iPhone 体验需独立验收。

最终备份在美国应用服务全部停止后生成，三库完整性检查通过；新加坡启动前按 SHA-256 逐项核对数据库和媒体文件。用户已有安装 ID 与云端对话保持不变，build 5 迁移本地草稿及当前会话。旧 build 3/4 内置美国地址，必须更新才能直接访问新加坡。

Apple 审核备注已改为新加坡独立审核地址，保留原审核凭证和合成录像。已批准的外部 build 2 保留手动服务连接入口。不要把手机内部演示构建直接当作外部审核隔离环境。

迁移过程、配置、最终应用备份和 AWS 快照记录保存在当前接续工作区的私有目录，不放入 Git。美国最终备份快照 `snap-0f6a87cd886b7b645` 已完成并保留；当前运行服务均在新加坡。

参考：[AWS Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html)、[Elastic IP](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/working-with-eips.html)。
