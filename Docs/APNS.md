# 手机通知接入

2026-10-14：已实现原生授权、设备登记、持久化推送队列、APNs HTTP/2 发送、失败重试和通知跳转。用户确认旧私钥没有备份并授权重建后，已创建新密钥，仅允许 `com.zhangmiao.evidenceguard` 的 Production 推送。私钥已保存于受限私有目录，并安装到新加坡手机服务；生产发送已启用，`/api/push/status` 返回 `serverReady=true`。旧密钥保留。TestFlight `1.0 (7)` 已完成处理、合规信息和内部组分发，组内显示“正在测试”。用户开启后已登记一台生产 iPhone；测试通知首次发送即被 Apple 接受，19 秒后收到手机鉴权点开的回执。锁屏展示及具体目标页面仍待用户反馈，任务/证据跳转需分别验收。

## 用户流程

build 8 已完成 Apple 处理并加入现有内部测试组，组内显示“正在测试”。本版将原来的「提醒偏好」和「通知与提醒」合并为「我的 → 通知与提醒」一个入口，旧入口路由也进入同一页。手机推送、摄像头主动提醒、每日概况和免打扰在页面内直接调整。首次开启手机推送弹出 iOS 授权窗口；仅在系统拒绝后显示前往系统设置的按钮。生产设备登记和权限规则不变，允许系统通知不会自动开启摄像头守护。

偏好更改自动保存，连续操作合并并按顺序发送；请求完成期间的新选择继续保存，旧结果不覆盖新选择。离开页面后保存继续执行，保存失败显示“更改尚未保存”和重试，重新进入同一服务保留待保存选择。切换服务后，旧请求的返回结果不能覆盖新服务设置。手机推送开关单独同步设备登记/停用，不会隐式修改助手偏好；关闭单台手机通知后，其助手偏好仍可保留供应用内使用。

测试按钮、权限状态、最近投递和刷新入口收进同页「测试通知与连接检查」。build 8 的分发状态以 [TestFlight](TESTFLIGHT.md) 为准；仍使用 build 7 时，主动偏好需在原页面点击“保存提醒偏好”。

手机后台可提醒：已通过现有策略的新事件、耗时任务结果、待确认草案。快速聊天不额外弹通知。锁屏只有通用短提示，不包含画面、录像链接、令牌或长消息；点开后通过当前服务鉴权读取详情，进入证据、任务或对应对话。历史回顾保留历史模式；原聊天草稿不被覆盖。

测试按钮只向当前登记手机发送一条测试通知，延迟 10 秒，每分钟最多一次。测试绕过应用免打扰时段，便于锁屏检查；仍受 iOS 权限、网络和专注模式影响。

## 发送策略与状态

- 持久化 `push_devices` / `push_outbox`；主动消息与推送入队在同一 SQLite 事务中完成。用户任务最终结果和推送入队同样一起提交。
- 每条来源每个安装实例只入队一次；重启恢复发送中的请求，保持同一 `apns-id` / collapse ID。网络中断时无法承诺严格恰好一次送达，折叠也不等于撤回已经显示的通知。
- 发送前重新核对开关、免打扰、已读/处理/稍后提醒、事件当前状态和时效。普通通知每天最多 6 条，间隔至少 5 分钟；前台心跳暂缓普通推送。默认最多保留一小时的待推送内容，不回填历史消息。
- 网络错误和 429 延后重试；5xx 至少等待 15 分钟，最多 6 次发送尝试。永久拒绝不盲目重试。无效令牌只停用收到拒绝的登记版本，不误停已更新的新令牌。
- `accepted` 只代表 Apple 接受请求；`opened_at` 仅在用户打开并成功鉴权读取时记录。没有把这些状态写成“手机已经收到”或“用户已经看懂”。关闭后已被 Apple 接受的通知无法保证撤回。

## 边界

服务仍是内部共享家庭空间，不是多租户账号系统。安装 ID 只作命名空间；设备登记另外需要本机 Keychain 中每个服务独立的随机凭证，以及现有服务访问令牌。手机、团队、Apple 审核数据库和访问令牌互相隔离。通知载荷仅有服务 scope 和不透明投递 ID，不能指定外部地址或扩展权限。

本次只升级 `evidenceguard-demo`。其独立 Python 环境为 `/opt/evidenceguard-demo/venv-apns`，通过 systemd drop-in 使用；团队与审核继续使用原运行环境。上线前已备份代码、环境和 SQLite。没有新增 AWS 实例、对外端口或测试员。

## 服务器配置

以下仅为配置名，不包含实际密钥；敏感文件只保存在受限私有目录与服务器 `/etc/evidenceguard-demo/`。

| 配置 | 用途 |
| --- | --- |
| `EG_PUSH_SCOPE=demo` | 当前服务的通知命名空间；其他环境必须使用不同值 |
| `EG_APNS_ENABLED=1` | 手机服务生产发送已启用 |
| `EG_APNS_TOPIC=com.zhangmiao.evidenceguard` | 允许的 App Bundle ID |
| `EG_APNS_TEAM_ID` | 现有 Apple Team ID |
| `EG_APNS_KEY_ID` | 与私钥对应的 Key ID |
| `EG_APNS_KEY_PATH` | 服务进程可读的 `.p8` 文件路径 |
| `EG_APNS_ENVIRONMENT=production` | 对应 TestFlight / App Store；开发包需独立开发环境密钥 |

私钥文件建议 `root:evidenceguard-demo`、`0640`，父目录 `0750`。配置只由运维写入；模型没有登记设备、改通知开关或发送任意推送的工具。设置密钥后重启手机服务，先验证 `/api/push/status` 的 `serverReady`，再从真实 iPhone 点击测试按钮。

接口均要求服务 Bearer Token、`X-EG-Installation-ID`、`X-EG-Push-Key`：

- `GET /api/push/status`：返回就绪和最近投递状态，不返回令牌、私钥或登记凭证。
- `PUT /api/push/device` / `DELETE /api/push/device`：登记/更新或关闭当前手机。
- `PUT /api/push/presence`：前台活动短租约。
- `POST /api/push/test`：当前手机的限频测试。
- `POST /api/push/deliveries/{id}/open`：检查归属，读取可信跳转目标并记录打开。

## 已验收与待验收

已通过 161 项 Cloud 测试，其中 15 项覆盖推送策略、去重、重启、令牌更新、鉴权隔离、HTTP 请求及 JWT。Swift 移动端边界检查通过。模拟器编译和通知设置页、系统权限弹窗、Keychain 存储已核对；模拟器额外声明 App 自身 Keychain 组，真实签名包使用相同组。带真实厂商 SDK 的 build 7 签名归档通过；最后的分发状态以 TESTFLIGHT.md 为准。

新生产密钥已安装，文件权限为 `root:evidenceguard-demo` / `0640`，启用前已备份配置及一致性 SQLite 快照。服务启动成功，实际 JWT 签名与鉴权就绪检查通过；三个服务的 HTTPS 证书、健康、匿名拒绝和跨环境令牌隔离均在服务器侧复核通过，手机及审核服务的外部媒体访问也通过。

2026-10-14 15:24（上海时间）：用户确认已开启通知，服务核对只有一台近期登记且启用的 Production 手机，随后向该手机入队一条 10 秒延迟的通用测试通知。Apple 首次请求即接受（15:24:22），手机鉴权读取测试目标并记录打开（15:24:41），没有失败原因。该记录验证了真实设备登记、APNs 发送和点开回传；不证明具体锁屏样式、所有目标页面或真实摄像头提醒已经验收。

真实 iPhone 验收顺序：在 TestFlight 直接更新到 `1.0 (8)`，保留本机数据 →「我的 → 通知与提醒」开启手机推送并允许系统权限 → 展开「测试通知与连接检查」，点击测试并在 10 秒内离开 App / 锁屏 → 收到测试通知 → 点击进入 → 服务记录打开。随后检查设置自动保存、任务/证据跳转、系统拒绝、重新授权、断网恢复、关闭推送和旧环境通知。上述测试不替代真实摄像头验收。

依据：[注册 APNs](https://developer.apple.com/documentation/usernotifications/registering-your-app-with-apns)、[Token 认证](https://developer.apple.com/documentation/usernotifications/establishing-a-token-based-connection-to-apns)、[APNs 响应与重试](https://developer.apple.com/documentation/usernotifications/handling-notification-responses-from-apns)。
