# 手机内部演示与 Personal Agent

本轮以原生 iOS 为唯一产品入口。打开即连接云端、直接发送消息，测试者不填写服务器、访问令牌或模型设置。Web 仓库未修改。

## 自动连接与部署

`MobileServiceConfiguration` 从私有构建配置读取演示服务与 demo 访问凭证。演示包忽略旧的 `serviceURL` 偏好，凭证只用于匹配的 HTTPS origin；连接错误分别显示断网、超时或测试版本授权失效。“我的 → 连接状态”只有状态与重新连接按钮。

专用演示服务使用 `evidenceguard-demo` Unix 用户、8792 回环端口、独立 SQLite / 录像目录和 Nginx HTTPS。系统服务开机启动；模型配置由现有服务复制到仅服务进程可读的环境文件。没有复制团队数据或 Apple 专用审核令牌。生成的测试录像有明确合成标识，已经完成索引。

模型 API Key 不在 App 中。内部包带有可提取、可撤销的 demo 访问凭证，它只能访问这套演示服务；这不是面向公众的账号体系。当前摄像头任务和对话仍属于团队演示空间。安装 ID 仅区分偏好，不能当成真实身份或多租户授权；只应使用测试资料。

## 实际架构顺序

1. 手机提供交互、扫描设备标识、确认记忆与规则、查看证据。
2. Personal Context 提供本次运行的已确认记忆、偏好及来源；临时记忆 24 小时后不再进入新运行。
3. Harness 冻结本轮模式、工具列表、摄像头 / Skill 范围及步数限制，检查工具列表漂移，持久化回执。历史对话上下文以完整轮次保留，字符预算 18,000。
4. 当前执行器 `bounded-chat-v1` 调云端模型，工具返回可检验的结果。草案不是新程序，不表示后台已具备对应执行能力。
5. Skill 执行器落实采样、验收和设备独占；CameraService 统一设备请求。历史查询只读已存资料。
6. Personal Agent 从已有任务事实生成事件提醒、5 分钟未处理提醒和每日概况，遵守时区与免打扰，写入 SQLite 提醒箱。按事件 / 日期去重，重启不重复投递。

对照的是已安装 MiiMiao v1.0 对照版源码 `c225f46465aaadf460bfc5e736a648192205323e`，其 Codex 版本为 0.153.4。参考了宿主掌握上下文和工具边界的原则；尚未把桌面 Codex App Server 执行器移植到本项目。当前主动提醒是三类固定只读流程，不是可以任意操作设备的通用规划器。

## 手机新增入口

- 首页文字使用独立浅色底，避免叠在背景树上。
- 首页 / 我的设备 → 扫描添加设备 → 确认序列号与位置 → 保存待连接记录。
- 我的 → 助手记忆与提醒：显式保存、移除、24 小时临时记忆，及提醒时间偏好。
- 首页 / 我的 → 助手提醒：来源、时间、已读状态与关联任务。

二维码解析只做有限的设备序列号提取，不打开二维码 URL、不执行其中内容。支持 T8171 / T8214 标识的保守格式；官方完整配网二维码协议尚待确认，未知格式引导手动输入。扫码没有完成官方绑定，也不会把设备标成在线。实际扫码相机权限与两款设备连接仍需 iPhone 和实物验收。

主动提醒默认关闭，由使用者选择开启。云端定时器不依赖手机常驻；当前仅有应用内收件箱，尚无 APNs 后台推送。标记提醒已读不改变 Skill 告警或现场结论。

## 构建与复核

私有 xcconfig 仅允许下面三个值，禁止放入模型 Key、团队主令牌或审核令牌。真实文件保持本机私有，不提交 Git。

```xcconfig
EG_INTERNAL_DEMO = YES
EG_SERVICE_BASE_URL = https:/$()/your-demo-host
EG_DEMO_ACCESS_TOKEN = <demo-only-token>
```

```bash
python3 scripts/archive_ios.py --team <TEAM> --bundle-id <BUNDLE> \
  --api-url https://your-demo-host --version 1.0 --build <NEXT_BUILD> \
  --demo-config /private/path/mobile-demo.xcconfig \
  --archive Release/EvidenceGuard-buildN.xcarchive --execute
scripts/check_mobile_contracts.sh
Cloud/.venv/bin/python -m pytest Cloud/server/tests -q
```

`cloud_demo_setup.sh` 在已部署的 Ubuntu 主机上创建隔离服务；源代码应先放到 `/opt/evidenceguard-demo/Cloud/server`。脚本复用已有 ACME 账号，不创建新的 EC2。`prepare_review_fixture.py --environment demo` 在 demo 目录生成并索引自有合成录像。

本轮验证：105 项 Cloud 测试通过；Swift origin / 二维码输入边界检查通过；模拟器构建及带真实 SDK 的 arm64 签名归档通过。通过额外全新 Bundle ID 验证了首次安装即自动连接；原生 UI 已验证真实回复、记忆写入后可被模型读出、待连接设备记录和返回操作。归档文件扫描未发现团队主令牌或模型 Key。Apple 分发校验通过，仍有厂商 WebRTC dSYM 缺失警告。1.0（3）已处理完成、补齐本轮出口合规信息并加入现有内部测试组；组内已显示“正在测试”。

后续必须分别验收：TestFlight 新包在用户手机上的网络与权限、官方 SDK 实物绑定 / 采集、APNs 后台送达、其他 Anker 产品适配，以及 Codex 执行器与当前模型协议兼容性。它们不由这次模拟器和模型连通测试代替。
