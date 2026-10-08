# iOS TestFlight 准备

Apple 的外部测试首个构建需要 Beta App Review。内部 TestFlight 测试和 Xcode 直接真机调试是不同路径，不要求先完成外部审核。本项目采用先验证设备，再准备外部 TestFlight 的流程；Web 开发和演示不等待该审核。

依据：[TestFlight overview](https://developer.apple.com/help/app-store-connect/test-a-beta-version/testflight-overview/)、[TestFlight](https://developer.apple.com/testflight/)。主办方若另有安装要求，以实际通知为准。

## 工程已准备

- `EvidenceGuard`：不链接官方 SDK，适合 Simulator 和 CI。
- `EvidenceGuardSDK`：iPhone arm64 的 SDK 方案；恢复资料包并完成 `SDK/prepare.py` 后使用生成的 workspace。
- Info.plist 版本与构建号读取 Xcode build settings，每次上传递增 `CURRENT_PROJECT_VERSION`。
- Release 云端地址来自 `EG_SERVICE_BASE_URL`，没有配置时显示待设置，不默认访问手机的 localhost。Release 服务连接只接受 HTTPS。
- `scripts/archive_ios.py` 默认只展示归档命令；加 `--execute` 才执行本地归档。该脚本不上传、不提交审核。

## 尚未具备发布条件

当前 SDK 的 `generateDummyFramework` 成功，但它只是 CocoaPods 占位框架。`pod install` 曾因官方依赖 CDN 下载超时未完成，实际 Kotlin/Native + SDK 真机编译尚未通过；模拟器成功不代表 SDK 编译成功。

还需准备 Apple Developer Program Team、该 Team 的 Bundle ID / App Store Connect 记录、签名，以及可供测试者访问的 HTTPS 云端。设备发现、真实画面、事件录像、断流恢复、麦克风、隐私说明和鉴权也要按实际行为完成验证。不能把当前版本描述成已通过 TestFlight 或真实守护验收。

## 执行步骤

1. 按 CONTRIBUTING 恢复 SDK，完成依赖安装。在 `EvidenceGuard.xcworkspace` 选 `EvidenceGuardSDK`，配置 Team，先用数据线安装真机测试；摄像头通过网络连接。
2. 使用实际账号与两个型号验证设备、媒体和交互。完成 Cloud 身份与媒体权限后部署 HTTPS 服务，确认离开开发机局域网也能访问。
3. 使用 App Store Connect 已登记的标识归档，例如：

```bash
python3 scripts/archive_ios.py \
  --team YOURTEAMID \
  --bundle-id com.yourteam.evidenceguard \
  --api-url https://你的真实服务域名 \
  --build 1
```

`YOURTEAMID` 是占位符，需替换成 10 位 Team ID。先看 dry run；核对后加 `--execute`。检查归档和 SDK 的符号/隐私清单，不自动添加未经核实的加密豁免声明。

4. 在 Xcode Organizer Validate / Distribute 到 App Store Connect，完成出口合规问答、Beta App 描述、反馈邮箱、审核联系信息、可用测试账号和所需设备访问说明。
5. 先内部测试；外部组的首个构建提交 Beta App Review，批准后再邀请团队外的测试者。审核结果与等待时间以 App Store Connect 实际状态为准。
