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

2026-10-09：开发机已有 Apple Developer Team 与开发证书，但 App Store Connect 应用记录、正式 Bundle ID、可访问的 HTTPS 后端尚未准备。`com.zhangmiao.evidenceguard` 是建议标识，尚未确认注册。摄像头及官方账号凭证到决赛才提供。目前没有完成签名分发、TestFlight 上传、Beta App Review 或真实设备验收。

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

## 正式归档与上传

1. 部署带用户身份和媒体访问控制的 HTTPS Cloud，验证蜂窝网络也能访问。现有本地 API 没有公网鉴权，不能直接暴露。
2. 在 Apple Developer / App Store Connect 建立本 Team 下的 Bundle ID 和 iOS 应用记录。配置签名、应用图标、Beta 描述、反馈邮箱、审核联系信息及实际可用的测试访问方式。
3. 使用真实服务地址归档：

```bash
python3 scripts/archive_ios.py \
  --team YOURTEAMID \
  --bundle-id com.yourteam.evidenceguard \
  --api-url https://你的真实服务域名 \
  --build 1
```

默认 dry run；核对后加 `--execute` 执行本地签名归档。`YOURTEAMID` 需替换为 10 位 Team ID。

4. 校验归档，再导出或上传：

```bash
python3 scripts/export_ios.py --team YOURTEAMID \
  --bundle-id com.yourteam.evidenceguard --action validate
python3 scripts/export_ios.py --team YOURTEAMID \
  --bundle-id com.yourteam.evidenceguard --action upload
```

同样默认 dry run；加 `--execute` 才执行。脚本检查归档的 Bundle ID、HTTPS 配置、SDK 框架和签名。上传只发送二进制，不自动提交 Beta App Review、接受协议或邀请测试者；也可用 Xcode Organizer 执行。

5. App Store Connect 处理完成后内部 TestFlight 验证安装、输入、语音权限与服务连接。外部测试提交首包 Beta App Review，通过后再邀请。还没有摄像头时，只能说明界面和构建验证范围，不能声称完整 SDK 功能已验收。
6. 决赛设备到位后，用官方凭证验证设备发现、事件时间、缩略图、真实录像、断流与恢复。主办方 demo 建议手机和设备使用同一 2.4 GHz Wi-Fi、关闭 AP 隔离；按现场实际配置核实。每项能力验证后才允许对应 Skill 发布。
