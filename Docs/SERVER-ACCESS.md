# EvidenceGuard 服务器与访问

2026-10-15 最新状态：手机 `evidenceguard-demo` 已启用官方 **Codex App Server 0.162.1**，使用原豆包模型。实际业务目录为 `/opt/evidenceguard-demo/releases/codex-20261015/Cloud/server`，由 `60-codex-runtime.conf` 指定；入口继续为 `eg_dashboard.bootstrap:app`，保留现有 Dashboard。该发布从当时实际运行的 `tools-6336a97c95c4bc5a` 复制，更新 `b4b2c16` 的 harness/runtime.py、harness/contract.py、harness/codex.py、assistant_identity.py 四个文件，保留同事硬件确认和操作回执。**不要再把 `/opt/evidenceguard-demo/Cloud/server` 当作当前运行目录；后续先核对 systemd ExecStart。** 线上三轮对话的 Codex 执行回执、三环境 HTTPS/令牌隔离、库完整性和源码哈希均通过。未分发新 App。详见 [执行器说明](CODEX-CLOUD.md) 和 [上线验证](verification/codex-cloud-2026-10-15.txt)。

2026-10-14：手机、团队联调和 Apple 审核服务已迁入新加坡。三套服务保留原来的独立账号、数据库、录像和访问令牌，每套只有一个应用进程。美国实例 `i-06744490347d73778` 已删除，AWS 已确认 `terminated`。旧地址不再提供服务，手机须在 TestFlight 更新到 `1.0 (5)`。

2026-10-15：仅手机 `evidenceguard-demo` 更新至应用代码 `904c5c8`，使用独立 `venv-build10`。上线前在关闭所有 worker 的备份库上验证迁移，正式切换前保存一致性数据库、源码和配置；首次运行权限检查失败已自动回滚，修复运行目录权限后重新上线。现在线上健康、模型就绪、数据库完整性和跨服务令牌隔离通过，进程无重启。Doubao 模型、Embedding 维数、APNs 和已有数据保持；新增独立连接器加密密钥用于手机信息快照，Gmail/飞书 OAuth 尚未配置。团队与 Apple 审核代码及数据未改。

同日聊天修复：手机服务在上述基线上热修复至 `8060b18` 的 `harness/runtime.py` 与 `assistant_identity.py`，移除无摄像头时覆盖整段回复的逻辑，并重启手机服务加载代码。其余文件、依赖、配置和数据库保持；团队与审核进程/源码未改。241 项测试及真实豆包连续 7 轮对话通过，部署后使用原问题的历史副本隔离复测身份回答通过。备份 `/root/evidenceguard-backups/chat-camera-fix-20261015`；见 [验证记录](verification/chat-camera-fix-2026-10-15.txt)。此修复无需新 App；SDK 闪退的客户端修复仍需单独分发。

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

手机当前源码在 `/opt/evidenceguard-demo/releases/briefings-20261015/Cloud/server`；团队和审核共用 `/opt/evidenceguard/Cloud/server`，只共用源码，不共用数据和凭证。模型密钥留在服务器的 `/etc/<服务名>/cloud.env`，不提交到 Git 或聊天。

三个 HTTPS 入口使用受信任证书，每六小时检查续期；三个证书的续期演练均已成功。地址依赖当前 Elastic IP，不能释放或更换它后仍期望旧地址有效。换笔记本 Wi-Fi 不会改变服务器地址。

## 管理连接

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

2026-10-15 早晚报告更新：手机服务使用 `70-briefing-runtime.conf` 指向上述 briefings release，保留 `eg_dashboard.bootstrap:app` 和现有 Codex/豆包配置。仅覆盖 8 个后端文件；上线前备份主库、硬件库、观测库及 drop-ins，在线身份与只读报告工具检查通过。配置摘要、其他环境 PID/配置/源码一致；未启用任何新订阅或分发安装包。详见 [早晚报告与验收](BRIEFINGS-AND-ACCEPTANCE.txt)。
