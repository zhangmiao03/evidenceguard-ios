# iOS TestFlight 准备

当前优先以 TestFlight 安装 iPhone 测试包，不需要数据线连接 Mac 或开启 Developer Mode。Xcode 直接安装是 Apple 支持的可选调试路径；外部 TestFlight 的首个构建需要 Beta App Review。开发编译无需等待该审核。

依据：[Developer Mode](https://developer.apple.com/documentation/xcode/enabling-developer-mode-on-a-device)、[TestFlight overview](https://developer.apple.com/help/app-store-connect/test-a-beta-version/testflight-overview/)、[上传构建](https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds/)。

## 手机内部演示更新

2026-10-16 build 11 分发完成：用户明确要求更新并恢复可写权限。源码基线 2cc803e 包含早晚报告独立设置、SDK 宿主闪退修复，以及将顶部 SDK 开关移到“我的 → 设置 → 开发调试 → 摄像头调试”。1.0 (11) 于 10:11 经 Xcode Organizer TestFlight Internal Only 上传；正式归档、真实 Release SDK、分发签名、production APNs、get-task-allow=false、服务地址与凭证匹配检查通过。沿用已核查的标准加密分类和不在法国分发范围，测试说明已保存。Apple 内部组页面已核对 build 11“正在测试”、90 天后过期；仅 EvidenceGuard Internal，仍为原 3 位测试员，8 个历史构建。build 9 和外部组未改，本轮未部署服务器。
验证：301 项云端测试及移动契约通过；本地原生 UI 测试 runner 超时未执行用例，不能算通过。GitHub CI 因账户付款/额度问题未启动，不能算 CI 通过。官方 AnkerWebRTC 缺少 dSYM 的既有上传警告保留。主动消息统一时间线尚未包含，真机 SDK 点击/新设置交互及实体摄像头链路仍待验收。当前可直接在 TestFlight 更新到 1.0 (11)，无需卸载。源码 2cc803e 已推送原 feat/anker-assistant 分支；原文件及保护快照保留。私有发布材料在本聊天 work/private/release-build11/，无需再次打包上传此构建。

2026-10-15 本轮分发：用户明确授权“分发吧”，目标为新构建 `1.0 (10)` 与既有 EvidenceGuard Internal 组，不新增测试员、不加入外部组。代码基线 `904c5c8` 包含 anker 机器人头像、自动记忆、只读连接应用、手机日历/提醒事项预览共享及定时摄像头观察。GitHub run `38622838553` 全部成功：Cloud 237、Linux 浏览器112、macOS WebKit56、iOS界面4项通过。新加坡手机服务已升级并通过备份库迁移、数据完整性、HTTPS、鉴权和三服务令牌隔离检查；团队与审核服务未变。Gmail/飞书 OAuth 尚待配置，真实摄像头及锁屏覆盖尚未验收。正式归档及真实 SDK 检查通过；命令行 Apple 账户校验失败后，改用 Xcode Organizer 的 TestFlight Internal Only 流程，于 09:18 上传成功。导出的 1.0 (10) 签名有效，APNs entitlement 为 production，get-task-allow 为 false。Apple 处理已完成；沿用已核查的标准加密分类及已确认的不在法国分发范围保存合规信息。测试说明已保存，构建只加入 EvidenceGuard Internal；组内核对为“正在测试”、90 天后过期，仍为原来的 3 位测试员。build 9 未分发，外部组未改。原厂 AnkerWebRTC 缺少匹配 dSYM 的既有非阻断警告仍保留。

2026-10-14 官方事件与助手更新：`1.0 (9)` 已完成带真实 SDK 的签名归档；App 标识、新加坡入口、APNs 配置和归档签名通过检查，分发签名及生产推送 entitlement 在导出后核对。SampleCore 的私有副本去签名后与 build 8 内容一致。摄像头主入口改为官方账号连接、设备事件和图片分析状态；开启后只在 App 前台同步，锁屏暂停。助手简化消息、重复标签和来源说明。手机 Cloud 已切换 `official_sdk` 并关闭合成场景，无设备时列表为空；165 项 Cloud 测试、6 项移动端契约检查和模拟器编译通过。本机上传首次因 Apple 导出阶段网络错误失败，重试后于 21:32 上传成功。用户要求先完成框架并统一分发：build 9 尚未加入内部或外部测试组，合规问卷尚未保存，当前可更新的仍为 build 8。只有用户明确要求分发后，才继续上传新构建或添加测试组。实体摄像头和 User ID / Token 未到位，真实事件、实际推送及后台覆盖尚未验收。见 [官方事件接入](OFFICIAL-CAMERA-EVENTS.md)。

2026-10-14 通知设置合并：`1.0 (8)` 将“提醒偏好”和“通知与提醒”合为一个页面，直接提供手机推送、摄像头事件、每日概况、时间与免打扰；更改自动保存，失败保留选择并可重试。系统拒绝权限时才提供跳转系统设置。模拟器编译、切换后立即离页再进入的保存检查，以及 6 项移动端契约检查通过；新增回归覆盖连续操作、请求中继续编辑、保存失败重试、服务切换后的晚返回。带真实 SDK 的签名归档通过，16:19 上传成功，Apple 处理与合规信息已完成。构建已加入现有 EvidenceGuard Internal 组，组内显示“正在测试”、90 天后过期，仍为原来的 3 位测试员；未加入外部组。当前内部测试请更新到 build 8，合并设置页的真机交互仍需分别验收。

2026-10-14 APNs 更新：`1.0 (7)` 包含五栏界面、手机通知授权/登记、测试入口和通知详情跳转；归档含 App 自身 Keychain 访问组及 APNs entitlement，真实官方 SDK 已核对。161 项 Cloud 测试通过。build 7 于 14:18 成功上传，Apple 处理已完成；沿用不变 SDK 的标准加密分类和已确认的不在法国分发范围保存合规问卷，测试说明已保存。构建已加入现有 EvidenceGuard Internal 组，组内显示“正在测试”、90 天后过期，仍为原来的 3 位测试员。build 7 没有加入外部组。用户已授权新建同范围 APNs 密钥，已安装到新加坡手机服务并启用，服务返回 `serverReady=true`；真实 iPhone 送达及点开仍待验收。详见 [APNs 接入](APNS.md)。

手机请在 TestFlight 直接更新到 `1.0 (10)`，保留本机数据。进入「我的 → 通知与提醒」开启手机推送、允许系统权限；在同页开启需要的摄像头提醒和每日概况，更改会自动保存。展开「测试通知与连接检查」，点击测试后在 10 秒内离开 App 或锁屏；检查收到通知及点开进入测试结果。

15:24 真机链路补充：用户开启通知后，服务已登记一台生产 iPhone；向该手机发送的测试通知被 Apple 首次接受，随后收到手机鉴权点开的回执。具体锁屏展示、测试结果页内容及任务/证据跳转仍需手机侧反馈，不把回执扩大为完整 UI 或摄像头验收。

build 6 为中间候选：通过 Apple 分发校验后，因提醒偏好文案需修订取消上传；最终使用 build 7。本轮刷新列表没有出现 build 6，未将其加入任何测试组。

2026-10-14：`1.0 (5)` 改为连接新加坡固定入口 `https://demo.47.131.21.137.sslip.io`。构建在启动时将旧美国服务名下的本地草稿、待发送请求和当前对话复制到新服务命名空间，保留安装 ID，不覆盖已存在的新服务数据，不迁移 Keychain 凭证；访问令牌继续严格绑定 HTTPS 来源。

已完成签名归档与 Apple 分发校验，已于 01:03 上传成功，Apple 处理完成；沿用不变的 SDK 加密分类和已确认分发范围保存合规问卷，构建加入现有 EvidenceGuard Internal 组。组内 `1.0 (5)` 已显示“正在测试”，仍为原来的 3 位测试员。官方 SDK 没有源码变化，本次复用与 build 4 UUID 一致且签名已核对的真实 Release `SampleCore.framework`（`4F781F23-B6CC-303B-B6E1-5F297979DCCB`），不是占位框架。原 AnkerWebRTC 缺少 dSYM 的非阻断警告仍存在。

迁移后，模拟器 App 显示“已自动连接 / 助手可以对话”，原聊天仍可读取，新消息得到真实模型回复。移动端来源边界与本地数据迁移检查通过。此结果不代表真实 iPhone、蜂窝网络或实际摄像头 SDK 验收。

Apple 审核备注已保存新加坡 review 地址，审核专用凭证与合成录像继续使用；外部 build 2 当前已显示“正在测试”，原“等待审核”记录属于历史状态。新版内部包不加入外部组。


2026-10-13：构建 `1.0 (4)` 已完成真实官方 SDK 的签名归档、Apple 分发校验和上传；02:51 上传后，App Store Connect 的处理状态已变为“完成”。沿用已核查的官方 SDK 标准加密分类和用户确认的不在法国分发范围保存出口合规问卷，构建状态变为“准备提交”。新的自动连接、独立对话、合成场景与证据追问测试说明已保存；构建 4 已加入现有 EvidenceGuard Internal 组，页面确认该构建只有这一个内部组，组内仍为原来的 3 位测试员、共 3 个构建。Mac 解锁后，已在该组的“构建版本”页核对 `1.0 (4)` 状态为“正在测试”、90 天后过期，内部测试员可以更新。这个分发结果不代表用户 iPhone 的功能验收已经通过。本轮未添加测试员、未提交新的外部审核、未创建公开邀请链接。

此包对应代码提交 `5e46158`；归档为 `Release/EvidenceGuard-build4-final.xcarchive`，保留真实 `SampleCore.framework`。官方 WebRTC 缺少匹配 dSYM 的非阻断警告仍存在。手机独立 demo 云端已升级，原生新版包含主对话/独立话题、草稿恢复、摄像头事件输入与确定性主动提醒、合成场景及证据追问。146 项 Cloud 回归及原生 Simulator 编译通过；模拟器收到实际模型生成的定时消息，已验证生成资料的标识和证据读取。

### 构建 5 手机验收顺序

1. 在 TestFlight 直接更新到 `1.0 (5)`（不要卸载，以保留本机数据），打开 App 等待自动连接。无需填写服务地址、Token 或模型 API；在「我的 → 连接状态」可查看连接结果。
2. 在 AI 页右上角新建话题，发一句测试消息。输入另一句但先不发送，退出并重新打开 App，检查草稿和原话题是否恢复；主对话及其他话题的记录应独立。
3. 进入「我的 → 测试主动守护场景」，先用“包裹离区”跑一次。检查三个标有合成测试水印的样本、实际模型核验、价值分和策略原因；点图片查看证据，在历史回顾中追问。这里不绑定设备、不启用真实 Skill，也不能证明真实拿走动作。
4. 如需验证主动消息，开启「关注摄像头事件与后续变化」，并单独开启「每日守护概况」；保存偏好。默认免打扰 22:00–08:00，普通事项 ≥80 分才进入即时候选，50–79 分待每日概况，<50 分静默。可为演示把概况时间设到当前小时，并把免打扰起止设为相同值；这个选择仅改变本安装实例的提醒偏好，不会强制模型发消息。
5. 有符合策略的事项后，到助手主对话查看主动卡片，展开“为什么提醒我”打开证据，再点“继续沟通”追问。验收重点是消息来源、已保存图片及诚实的能力限制；当前只有应用内通知，锁屏不弹系统推送。

尚未在用户 iPhone 上验收蜂窝网络、系统权限、崩溃与实际摄像头 SDK；以上是待执行的手机测试清单，不把模拟器验证当成真机通过。

2026-10-12：`1.0 (3)` 使用独立手机演示服务，安装后自动鉴权连接，不要求测试者填写 URL 或 Token；原模型 Key 仍只在服务器。已完成签名归档、Apple 分发校验、上传和 Apple 处理。沿用本轮未改动的官方 SDK 加密分类及用户已确认的不在法国分发范围完成问卷；构建 3 已加入现有 EvidenceGuard Internal 组，组内状态为“正在测试”（官方 WebRTC 的 dSYM 警告仍存在）。没有新增测试员或公开邀请链接；旧的 `1.0 (2)` 不会因为云端部署自动获得新启动流程，手机需要安装新构建。

内部演示隐藏 SDK 账号配置页面，提供扫码识别与“待官方绑定核验”流程。旧开发构建继续保留工程联调入口。见 [手机演示构建说明](MOBILE-DEMO-PERSONAL-AGENT.md)。

## 工程与联调入口

- `EvidenceGuard`：不链接官方 SDK，用于 Simulator 和 CI。
- `EvidenceGuardSDK`：链接赛事提供的 arm64 SDK，使用 `EvidenceGuard.xcworkspace`；不能在 Simulator 执行。缺失真实 `SampleCore` 时编译会明确失败。
- App 的「我的 → 官方摄像头接入」保存赛事 User ID / Token 到本机 Keychain，查询实际设备。发现 T8171 / T8214 后可进入「检查图片与历史事件」。
- 设备联调页读取 SDK 缩略图并按 iPhone 当前时区查询自然日事件，最多 50 条；缩略图标明历史或缓存来源。查询无事件不能证明现场没有活动。
- SDK → Cloud 只读事件元数据/实际缩略图导入已实现，按事件合并核验和计费预算运行；手机前台同步不能证明锁屏后持续接收。真实摄像头采集、实时守护和设备控制仍待实物联调；导入成功不能解除真实 Skill 的发布限制。
- Release 云端地址来自 `EG_SERVICE_BASE_URL`，未配置时显示待设置；正式服务连接要求 HTTPS。
- 版本和构建号读取 Xcode build settings，每次上传递增 `CURRENT_PROJECT_VERSION`。

## 当前外部条件

2026-10-11：Team `996JX76BJT` 下已注册显式 Bundle ID `com.zhangmiao.evidenceguard`，并创建 [EvidenceGuard 应用记录](https://appstoreconnect.apple.com/apps/6821409514/distribution)。`1.0 (1)` 虽然返回上传成功，随后被 Apple 的处理邮件以 ITMS-90683 拒绝。已补齐四项用途说明，带真实 SDK 的 `1.0 (2)` 已签名归档、通过分发校验，上传返回 `Upload succeeded` / `EXPORT SUCCEEDED`；Apple 处理已完成。随后通过 SDK 静态核查及用户确认的分发范围保存加密问卷，解除“缺少出口合规证明”。构建 2 已提交 Beta App Review，[外部测试群组](https://appstoreconnect.apple.com/teams/5151fc77-8a5a-4d6f-b0f9-40e28f979db0/apps/6821409514/testflight/groups/2cb84fc9-6660-4b83-a513-f46f3fd35cdb) 实际显示“正在等待审核”。归档嵌入 `https://34.218.51.85`，App 和各依赖 framework 保留不同 Bundle ID。Apple 审核通过、iPhone 安装及真实摄像头验收尚未完成。先前网页登录和 `Error Downloading App Information` 问题已在应用记录建立后解除。

首包邮件的阻断项为 `NSContactsUsageDescription`、`NSMotionUsageDescription`，警告项为 `NSLocationWhenInUseUsageDescription`、`NSBluetoothAlwaysUsageDescription`。App 没有新增通讯录或 CoreMotion 授权调用，对应说明明确本测试版不需要这两项授权。位置和蓝牙说明参考官方 demo 的 Wi-Fi 发现与 IoT 设备配网用途；摄像头画面中的移动检测不等于手机运动与健身数据。`export_ios.py` 会检查实际归档中的用途字符串非空，再执行分发操作。

09:12 本机时间，TestFlight 的“构建版本上传”列表已出现 `1.0 (2)`，状态为“正在处理”；`1.0 (1)` 显示“失败”。可测试的构建列表当时仍为空，不能把上传列表的记录当成已可安装的测试包。

随后上传状态变为“完成”，构建 2 出现在正式构建表中。初次打开“管理”时，Apple 问卷要求区分专有/非标准算法、非 Apple 系统实现的标准算法、两者兼用、均不属于；当时未选择未经核实的声明。后续 SDK 核查和实际保存结果见下文。

分发警告：官方 `AnkerWebRTC.framework` 没有匹配的 dSYM（UUID `4C4C4445-5555-3144-A1F4-EEDE4345040C`）。此警告未阻断校验或上传，但会限制厂商库崩溃定位；需向主办方索取匹配符号，不能生成空文件冒充。

2026-10-10：AWS Cloud 已部署，受信任 HTTPS 地址为 `https://34.218.51.85`。匿名数据接口 401、鉴权 bootstrap 200、实际文本模型对话调用成功；媒体 Cookie 的 Range/206、HEAD 和缩略图访问通过公网检查。IP 证书每六小时检查续期，续期演练通过。100 项 Cloud 测试及 iOS 编译通过。

历史记录（2026-10-09）：当时仅有 Apple Developer Team 与开发证书，尚未准备 App Store Connect 应用记录、正式 Bundle ID 和 HTTPS 后端。该阶段未完成签名分发或上传；以上状态已由 10 月 11 日记录更新。摄像头及官方账号凭证仍待决赛提供。

SDK 公共依赖已安装，实际 `EvidenceGuardSDK` 的 iPhone arm64 Debug 构建、未签名 Release 归档和普通 iOS Simulator 构建均已通过；真实框架与 Compose 资源已打包。未签名归档仅作构建验证，不能安装或上传 TestFlight。`generateDummyFramework` 只是 CocoaPods 初始化占位框架，不能用它证明官方 SDK 已编译。

## 本机编译

按 CONTRIBUTING 恢复 SDK、安装 JDK / CocoaPods 并运行 `SDK/prepare.py`。用以下命令检查实际 iPhone SDK 编译，无需接手机或登录摄像头：

```bash
xcodebuild -workspace EvidenceGuard.xcworkspace \
  -scheme EvidenceGuardSDK -configuration Debug \
  -destination 'generic/platform=iOS' CODE_SIGNING_ALLOWED=NO build
```

官方 demo 要求首次真实框架生成后再次 `pod install` 并重建，使 Compose 资源被 CocoaPods 收录。使用 `SDK/.tools/bin/pod install` 或团队 Bundler 命令；不要只打开初始化占位工程上传。

Podfile 对齐官方 SampleCore 的 Mach-O 最低 iOS 版本与 Info.plist，保留 Release 的正常符号处理。App 已声明自身 UserDefaults 的 CA92.1 用途（保存本 App 服务地址与会话 ID），图标已无透明通道。AWS 依赖带有其隐私清单；官方 SDK / 其他原生库的完整清单和符号仍需核实，不能用 App 的声明代替厂商声明，也不自动填写未经核实的加密豁免。依据：[Apple required reason API](https://developer.apple.com/documentation/bundleresources/describing-use-of-required-reason-api)。

## 首包测试说明草案

Beta 描述：EvidenceGuard 是安克黑客松的原生 iOS 视觉任务原型。测试内容包括助手文字输入与语音转文字、摄像头选择、Skill 草案编辑和区域圈选，以及手动导入录像后的检索、复核与证据播放。云端需要团队提供的测试访问方式；录像识别结论需查看原片核对。官方摄像头入口已集成 SDK，但实体设备与赛事账号尚未到位，本轮不验证真实摄像头或持续实时守护。

测试顺序：安装 →「我的 → 服务连接」配置测试地址及令牌 → AI 输入文字 → 查看草案并进入编辑 → 导入公开或自有非敏感短片 → 在历史回顾中查询 → 点击证据定位播放。记录服务连接失败、输入/返回/圈选交互问题、时间定位与原片不一致，以及崩溃；同时标明 Wi-Fi 或蜂窝网络、iOS 版本及 App 构建号。尚未用安装后的 iPhone 跑通此顺序，不能据此承诺验收完成。

用户在测试信息页自行填写审核联系人后，已核对并保存；反馈邮箱使用同一联系邮箱，中国手机号码规范为 +86。联系信息不写入版本库。独立审核访问已准备并验证。当前 Cloud 是单团队共享数据空间，不能把现有团队令牌直接当成公开测试账号；审核访问已使用隔离测试数据和单独的令牌，不把模型 Key、摄像头 Token 或成员私密录像交给审核员。Beta 描述、审核操作说明、审核访问和联系人资料均已保存到 App Store Connect，并随构建 2 提交 Beta App Review。

已在同一 EC2 准备独立审核服务 `https://review.34.218.51.85.sslip.io`：独立 Unix 用户、数据库、录像目录、进程和令牌，与团队服务使用不同 HTTPS 主机名。公网验证已通过 TLS、匿名 401、两个令牌互用 401，以及审核媒体 Cookie 的 Range/206、HEAD 和 JPEG；媒体 Cookie 不能读取普通数据接口。用户明确授权仅供 Apple 审核后，专用令牌已填写到 App Store Connect 的审核登录信息；页面返回“已保存”。令牌不写入仓库，审核备注解释 App 使用服务地址和令牌、用户名仅为审核标签。

审核库只预置一段自生成的 10 s 水印视频，标题与来源明确标为合成测试，不复制团队录像或许可不明的公开视频；采集日期未知。实际 Embedding 索引已完成，但不代表真实场景识别或守护验收。实际历史对话已调用检索和视频模型复核，返回 uncertain 候选且未编造采集日期；这是传输与调用验证，不是现实场景识别验收。可先测试录像库播放、拖动定位和历史查询。实体摄像头不在线，实时能力限制保留。

## 官方 SDK 加密核查（2026-10-11）

对给定 SDK 包和实际上传的 `1.0 (2)` 归档进行了静态核查。本次证据支持选择 Apple 问卷的“代替在 Apple 操作系统中使用或访问加密，或与这些操作同时使用的标准加密算法”。不是仅使用 Apple 操作系统的加密。未发现专有或非标准加密算法的证据；这是依据已检查实现作出的技术判断，不是厂商出具的分类证书，也不是对所有闭源路径的完整证明。

核查范围是 ESIotKit `2.2.7`、iOS `iot-crypto 2.2.6.7.dev.8`、P2P / 视频框架的官方头文件、Kotlin Native KLIB 中间表示，以及实际归档中 `SampleCore` 的符号和选定加密函数的反汇编。没有运行 SDK 二进制，也没有向外上传厂商代码或凭证。符号存在证明代码被打包；目前没有实体摄像头，不能据此断言两型号现场会选择哪条算法分支。

| 检查对象 | 实际证据 | 对分类的意义 |
| --- | --- | --- |
| `iot-crypto` iOS KLIB | `IotAESImpl` 调用标准 AES provider；`getEcdh.ios.kt` 和 `EccEncryption.iosArm64.kt` 使用 ECDH / P-256、AES-CBC、HMAC；`AesUtil` 使用 AES-GCM；依赖包含 Apple / CryptoKit provider | 厂商对标准算法的封装；SDK 自有类名不等于自研加密算法 |
| P2P 官方头文件 | `enc_decrypt_interface.h`、`eufy_enc_decrypt_interface.h`、`p2p_cryptography.h` 引用 OpenSSL AES / RSA，声明 AES-GCM 128 / 256；协议枚举注明 RSA + AES、AES-GCM / ECB | 提供 App SDK 自身的算法证据，不再仅依赖 Web 文档 |
| 归档 `SampleCore` | `_aes_encrypt_eufy` 调用 OpenSSL `_AES_ecb_encrypt`；`_aes_gcm256_encrypt` 调用 `_EVP_aes_256_gcm`；`_p2p_agent_rsa_decrypt` 调用 `_RSA_private_decrypt` | 实际包包含非 Apple 系统实现的标准加密 |
| 归档 `SampleCore` 的另一 P2P 路径 | `_aesEncryptByKey` 调用 `mbedtls_aes_crypt_ecb`；`_rsaEncryptByPubkey` 调用 `mbedtls_rsa_pkcs1_encrypt` | 再次确认不能选择“仅使用 Apple 系统加密” |
| 厂商 ECC 媒体封装 | `_ecc_EncryptECC` / `_ecc_DecryptECC` 调用椭圆曲线点运算、KDF、HMAC-SHA256 和 AES-CBC；`_zx_ecc_encrypt` 调用 AES-GCM | 已检查的厂商封装建立在可识别的密码学算法上；没有把协议封装误判为独立密码算法 |
| SQLCipher / SSZipArchive | SQLCipher 实际构建设置为 `SQLCIPHER_CRYPTO_CC`，源码调用 CommonCrypto AES-256 / PBKDF2 / HMAC；SSZipArchive 的 Apple crypto backend 调用 CommonCrypto AES | 这两项本身不能作为“自带 OpenSSL”的证据；非 Apple 实现的依据来自上述 P2P 实际调用 |

头文件和协议枚举还包含 RC4 兼容路径，归档带有多种密码库兼容实现。它们的存在不证明当前摄像头正在使用，也不代表本次做过安全强度或协议安全性验收。本次没有找到 SDK 提供的 TestFlight 填写说明、CCATS 编号或加密声明文件。

实际归档指纹（SHA-256）：

- `SampleCore.framework/SampleCore`：`139c72b1e41a26e29228edeee51ae1647cc78595b777645d5bba1b5dd282ad5e`
- `AnkerWebRTC.framework/AnkerWebRTC`：`d864865da029d31b7da406d4eec0765f12354ef84dd66230f15b2b88d4e772e9`

用户明确确认目前不在法国分发，仅团队和赛事测试。已按“标准加密算法 → 不在法国分发”保存构建 2 的问卷，TestFlight 实际状态由“缺少出口合规证明”变为“准备提交”。依据：[Apple 加密文稿要求](https://developer.apple.com/help/app-store-connect/reference/app-information/export-compliance-documentation-for-encryption/)。这次未修改 `ITSAppUsesNonExemptEncryption` 来跳过问卷，未移除官方 SDK，也没有填写未经提供的 CCATS / 法国声明。更换 SDK 或扩大分发范围，尤其涉及法国时，需要重新核查；主办方后续说明若与静态核查冲突，应及时更正。

问卷保存后，按 [Apple 外部测试流程](https://developer.apple.com/help/app-store-connect/test-a-beta-version/invite-external-testers/) 先创建 `EvidenceGuard Internal` 内部群组，关闭自动分发，未添加测试员或构建；再创建 `EvidenceGuard Hackathon` 外部群组，添加 `1.0 (2)`、核对测试范围、关闭自动通知并提交审核。页面已确认“外部群组 ∙ 0 个测试员 ∙ 1 个构建版本”及“正在等待审核”。未发送邀请、未创建公开链接、未扩大审核令牌的授权范围。审核通过后才安排外部测试员安装与验收。

## 正式归档与上传

1. 使用已配置访问令牌与媒体权限的 HTTPS Cloud；仍需用安装后的 iPhone 验证蜂窝网络连接。
2. 在 Apple Developer / App Store Connect 建立本 Team 下的 Bundle ID 和 iOS 应用记录。配置签名、应用图标、Beta 描述、反馈邮箱、审核联系信息及实际可用的测试访问方式。
3. 使用真实服务地址归档：

```bash
python3 scripts/archive_ios.py \
  --team YOURTEAMID \
  --bundle-id com.yourteam.evidenceguard \
  --api-url https://team.47.131.21.137.sslip.io \
  --build 2
```

默认 dry run；核对后加 `--execute` 执行本地签名归档。`YOURTEAMID` 需替换为 10 位 Team ID。脚本仅通过 `EG_APP_BUNDLE_ID` 设置 App 标识，保留第三方 framework 的自身标识。

4. 校验归档，再导出或上传：

```bash
python3 scripts/export_ios.py --team YOURTEAMID \
  --bundle-id com.yourteam.evidenceguard --action validate
python3 scripts/export_ios.py --team YOURTEAMID \
  --bundle-id com.yourteam.evidenceguard --action upload
```

同样默认 dry run；加 `--execute` 才执行。脚本检查归档的 Bundle ID、HTTPS 配置、SDK 框架、权限用途字符串和签名。上传只发送二进制，不自动提交 Beta App Review、接受协议或邀请测试者；也可用 Xcode Organizer 执行。

5. App Store Connect 处理完成后内部 TestFlight 验证安装、输入、语音权限与服务连接。外部测试提交首包 Beta App Review，通过后再邀请。还没有摄像头时，只能说明界面和构建验证范围，不能声称完整 SDK 功能已验收。
6. 决赛设备到位后，用官方凭证验证设备发现、事件时间、缩略图、真实录像、断流与恢复。主办方 demo 建议手机和设备使用同一 2.4 GHz Wi-Fi、关闭 AP 隔离；按现场实际配置核实。每项能力验证后才允许对应 Skill 发布。
