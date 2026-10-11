# iOS TestFlight 准备

当前优先以 TestFlight 安装 iPhone 测试包，不需要数据线连接 Mac 或开启 Developer Mode。Xcode 直接安装是 Apple 支持的可选调试路径；外部 TestFlight 的首个构建需要 Beta App Review。开发编译无需等待该审核。

依据：[Developer Mode](https://developer.apple.com/documentation/xcode/enabling-developer-mode-on-a-device)、[TestFlight overview](https://developer.apple.com/help/app-store-connect/test-a-beta-version/testflight-overview/)、[上传构建](https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds/)。

## 手机内部演示更新

2026-10-12：`1.0 (3)` 使用独立手机演示服务，安装后自动鉴权连接，不要求测试者填写 URL 或 Token；原模型 Key 仍只在服务器。已完成签名归档、Apple 分发校验及上传；App Store Connect 在 02:09 接收并显示“正在处理”（官方 WebRTC 的 dSYM 警告仍存在）。可安装状态以构建处理和测试组分配为准；旧的 `1.0 (2)` 不会因为云端部署自动获得新启动流程，手机需要安装新构建。

内部演示隐藏 SDK 账号配置页面，提供扫码识别与“待官方绑定核验”流程。旧开发构建继续保留工程联调入口。见 [手机演示构建说明](MOBILE-DEMO-PERSONAL-AGENT.md)。

## 工程与联调入口

- `EvidenceGuard`：不链接官方 SDK，用于 Simulator 和 CI。
- `EvidenceGuardSDK`：链接赛事提供的 arm64 SDK，使用 `EvidenceGuard.xcworkspace`；不能在 Simulator 执行。缺失真实 `SampleCore` 时编译会明确失败。
- App 的「我的 → 官方摄像头接入」保存赛事 User ID / Token 到本机 Keychain，查询实际设备。发现 T8171 / T8214 后可进入「检查图片与历史事件」。
- 设备联调页读取 SDK 缩略图并按 iPhone 当前时区查询自然日事件，最多 50 条；缩略图标明历史或缓存来源。查询无事件不能证明现场没有活动。
- 未接入 SDK → Cloud 媒体导入、实时守护或设备控制。这些入口成功不能解除真实 Skill 的发布限制。
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
