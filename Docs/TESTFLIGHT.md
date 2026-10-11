# iOS TestFlight 准备

当前优先以 TestFlight 安装 iPhone 测试包，不需要数据线连接 Mac 或开启 Developer Mode。Xcode 直接安装是 Apple 支持的可选调试路径；外部 TestFlight 的首个构建需要 Beta App Review。开发编译无需等待该审核。

依据：[Developer Mode](https://developer.apple.com/documentation/xcode/enabling-developer-mode-on-a-device)、[TestFlight overview](https://developer.apple.com/help/app-store-connect/test-a-beta-version/testflight-overview/)、[上传构建](https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds/)。

## 工程与联调入口

- `EvidenceGuard`：不链接官方 SDK，用于 Simulator 和 CI。
- `EvidenceGuardSDK`：链接赛事提供的 arm64 SDK，使用 `EvidenceGuard.xcworkspace`；不能在 Simulator 执行。缺失真实 `SampleCore` 时编译会明确失败。
- App 的「我的 → 官方摄像头接入」保存赛事 User ID / Token 到本机 Keychain，查询实际设备。发现 T8171 / T8214 后可进入「检查图片与历史事件」。
- 设备联调页读取 SDK 缩略图并按 iPhone 当前时区查询自然日事件，最多 50 条；缩略图标明历史或缓存来源。查询无事件不能证明现场没有活动。
- 未接入 SDK → Cloud 媒体导入、实时守护或设备控制。这些入口成功不能解除真实 Skill 的发布限制。
- Release 云端地址来自 `EG_SERVICE_BASE_URL`，未配置时显示待设置；正式服务连接要求 HTTPS。
- 版本和构建号读取 Xcode build settings，每次上传递增 `CURRENT_PROJECT_VERSION`。

## 当前外部条件

2026-10-11：Team `996JX76BJT` 下已注册显式 Bundle ID `com.zhangmiao.evidenceguard`，并创建 [EvidenceGuard 应用记录](https://appstoreconnect.apple.com/apps/6821409514/distribution)。`1.0 (1)` 虽然返回上传成功，随后被 Apple 的处理邮件以 ITMS-90683 拒绝。已补齐四项用途说明，带真实 SDK 的 `1.0 (2)` 已签名归档、通过分发校验，上传返回 `Upload succeeded` / `EXPORT SUCCEEDED`；Apple 处理已完成，TestFlight 列出构建 2，状态为“缺少出口合规证明”。归档嵌入 `https://34.218.51.85`，App 和各依赖 framework 保留不同 Bundle ID。尚未完成出口合规确认、Beta App Review、iPhone 安装或真实摄像头验收。先前网页登录和 `Error Downloading App Information` 问题已在应用记录建立后解除。

首包邮件的阻断项为 `NSContactsUsageDescription`、`NSMotionUsageDescription`，警告项为 `NSLocationWhenInUseUsageDescription`、`NSBluetoothAlwaysUsageDescription`。App 没有新增通讯录或 CoreMotion 授权调用，对应说明明确本测试版不需要这两项授权。位置和蓝牙说明参考官方 demo 的 Wi-Fi 发现与 IoT 设备配网用途；摄像头画面中的移动检测不等于手机运动与健身数据。`export_ios.py` 会检查实际归档中的用途字符串非空，再执行分发操作。

09:12 本机时间，TestFlight 的“构建版本上传”列表已出现 `1.0 (2)`，状态为“正在处理”；`1.0 (1)` 显示“失败”。可测试的构建列表当时仍为空，不能把上传列表的记录当成已可安装的测试包。

随后上传状态变为“完成”，构建 2 出现在正式构建表中。打开“管理”后，Apple 问卷要求区分专有/非标准算法、非 Apple 系统实现的标准算法、两者兼用、均不属于。四项均未选择，也未保存未经核实的加密声明。

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

用户在测试信息页自行填写审核联系人后，已核对并保存；反馈邮箱使用同一联系邮箱，中国手机号码规范为 +86。联系信息不写入版本库。独立审核访问已准备并验证。当前 Cloud 是单团队共享数据空间，不能把现有团队令牌直接当成公开测试账号；审核访问已使用隔离测试数据和单独的令牌，不把模型 Key、摄像头 Token 或成员私密录像交给审核员。Beta 描述、审核操作说明、审核访问和联系人资料均已保存到 App Store Connect，未提交 Beta App Review。

已在同一 EC2 准备独立审核服务 `https://review.34.218.51.85.sslip.io`：独立 Unix 用户、数据库、录像目录、进程和令牌，与团队服务使用不同 HTTPS 主机名。公网验证已通过 TLS、匿名 401、两个令牌互用 401，以及审核媒体 Cookie 的 Range/206、HEAD 和 JPEG；媒体 Cookie 不能读取普通数据接口。用户明确授权仅供 Apple 审核后，专用令牌已填写到 App Store Connect 的审核登录信息；页面返回“已保存”。令牌不写入仓库，审核备注解释 App 使用服务地址和令牌、用户名仅为审核标签。

审核库只预置一段自生成的 10 s 水印视频，标题与来源明确标为合成测试，不复制团队录像或许可不明的公开视频；采集日期未知。实际 Embedding 索引已完成，但不代表真实场景识别或守护验收。实际历史对话已调用检索和视频模型复核，返回 uncertain 候选且未编造采集日期；这是传输与调用验证，不是现实场景识别验收。可先测试录像库播放、拖动定位和历史查询。实体摄像头不在线，实时能力限制保留。

加密信息需按实际 SDK 回答：[Apple 加密文稿说明](https://developer.apple.com/help/app-store-connect/manage-app-information/determine-and-upload-app-encryption-documentation/)。依赖中有 SQLCipher 和 AnkerWebRTC，不能仅根据 App 使用 HTTPS 就勾选“仅使用 Apple 操作系统加密”；还需确认厂商 SDK 的加密实现与适用的分发范围。

向主办方核实：App SDK 是否只使用行业标准加密算法，是否包含自研或非标准算法，以及是否有供 TestFlight / App Store 使用的出口合规说明。现有 App 手册提到 `needEncrypt` 默认启用 SDK 加密，但没有给出算法或出口分类；Web 文档的 ECDH 描述不能代替 App SDK 的声明。

## 正式归档与上传

1. 使用已配置访问令牌与媒体权限的 HTTPS Cloud；仍需用安装后的 iPhone 验证蜂窝网络连接。
2. 在 Apple Developer / App Store Connect 建立本 Team 下的 Bundle ID 和 iOS 应用记录。配置签名、应用图标、Beta 描述、反馈邮箱、审核联系信息及实际可用的测试访问方式。
3. 使用真实服务地址归档：

```bash
python3 scripts/archive_ios.py \
  --team YOURTEAMID \
  --bundle-id com.yourteam.evidenceguard \
  --api-url https://34.218.51.85 \
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
