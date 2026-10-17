# 2026-10-16 官方 Web Token 修正与硬件边界

## 来源与实际变化

官方包：`web-sdk-hackathon-demo-1016-1411.zip`，SHA-256 `924ab67c7c0e9d065c248f685921ec68bbe062479bbb954a885936686eafb010`。

包内 `public/sdk/index.js` 为 4,858,053 字节，SHA-256 `316bfc1edb3cf5c35ed24e7fa9fd0caa1867bc111181c9a58348f86dee97f02e`，与原交付相同。此次修正发生在 `src/config.ts`、`src/components/AuthForm.tsx`、`src/services/connect.ts`，增加现成 Token 登录，默认选择这一路线。

旧路线：account_uuid → 密钥交换 → `request_token` → 获得新 Token。根据官方本次说明，重新生成会使旧 Token 失效。新路线：直接将现成 Token 传入 `OpenAPIIntegration.authorization`，不调用 `request_token`。播放器自身建立加密连接仍可能做 ECDH；ECDH 不等于刷新 Token。

## 当前产品实现

- `Web/src/sdk.ts`：新增直接 Token 分支，以官方 UMD 做 ECDH 和 `getWSSign()` 验证，成功后给播放器创建独立 integration。没有收到有效信令签名不能宣告账号鉴权通过。断开账号中止在途请求；无自动回退到刷新 Token 的分支。
- `Web/src/App.tsx`：默认 Token 直连，原参数方式保留刷新提示；切换官方工作区时通过同源握手在内存传入 Token，返回或断开清空。导入 SN 仍不等于配网、绑定或官方所有权认证。
- `Web/src/sdk-transport.ts`：SDK POST 先物化请求体再转发，兼容 localhost HTTP/1.1；抑制来自原始 UMD 的 JavaScript 控制台日志，避免 SDK 打印密钥和签名地址。正常开发诊断保留。
- `Web/official-host/main.tsx`：复用上述代理处理；官方 UMD 与播放器未改写。
- `scripts/import_official_web_demo.py`：继续只使用内存保存配置；拒绝非空默认 Token，移除预置团队凭据，隐藏 Token 输入，去掉旧路线日志中的 Token 原文。这些宿主适配写入导入 manifest，不宣称官方 UI 源码逐字节未改动。
- `EvidenceGuard/OfficialSDKConnection.swift`：原先已支持 User ID + Token + PR/QA，使用本机 Keychain；本次没有改成账号密码换取流程，也没有把真实 Token 写入源码。
- Cloud `/api/sdk/openapi/*` 继续固定官方 US 域名代理。设备登记、媒体会话、新帧 challenge、工具确认/回执接口不变。

## 已知硬件边界

| 能力 | Web 直接连接 | iOS / Android 原生 SDK | 本项目落实情况 |
|---|---|---|---|
| T8171 / T8214 Live 取流 | 有 | 有 | 2026-10-16 用户手动反馈 Web 取流正常；未提供逐台首帧/时长等数值 |
| 视频解码后采样 | 有 SDK 订阅/播放器逐帧路线 | 有原生播放器取样路线 | 已有新帧挑战逻辑；本次手动取流反馈不等于 Agent 收图和视觉理解已验收 |
| T8171 左右/上下云台、预置位 | 本次 mediachannel 路线不支持；仿制按钮无效 | 有原生控制接口 | Web 只能委派在线 iOS 执行器，控制需确认与真机记录 |
| T8214 云台 | 不是门铃能力 | 不作为门铃测试项 | 不显示成可用云台能力 |
| 设备设置、对讲、历史录像、首次配网 | 本次 Web Demo 不覆盖完整原生能力 | 按型号使用原生 API 验证 | 不把通用 UMD 的同名方法当作当前两款设备的可用接口 |
| Web/App 共用现成 Token | 不主动刷新 Token | 使用相同有效 Token | 官方修复解决登录刷新问题；不证明同一设备可同时开多路媒体连接 |

用户进一步明确 T8214 的两个镜头：前向主摄是面向门口的广角摄像头，第二摄像头朝向门下。官方包 `docs/API参考手册.md:220` 与 `docs/开发指南.md:221` 明确两路画面在设备端拼成一路视频下发，Web 按单路处理；开发指南还说明在 App 调整拼接方式后，Web 会自动切换。此处是文档能力，不是本次已完成调整操作的回执。

产品展示和 Agent 提示分别关联“来访者/门口活动”与“门槛/包裹”，不将视角用途写成已看到的现场事实。两个视角仍属于同一 SN；不预设上下或左右排列，不把重叠目标重复计数。当前协议 `channelId=main` 是逻辑 SDK 视频输入，并非“前向物理主摄”的保证。原生端具体布局、镜头操作和独立取帧仍须 SDK 与真机核验。

浏览器要求以包内 `docs/开发指南.md` 与 `docs/赛前准备清单.md` 为准：Chrome，关闭 `WebRTC PQC for DTLS` 后重启。产品页面在 Firefox/WebKit 的兼容测试通过，不等于官方设备媒体链路在这些浏览器上通过。

## 验证记录与未完成项

1. **用户真机反馈**：2026-10-16 明确反馈 Web 手动取流正常；左右控制不能靠网页仿制，须原生 SDK。此项来源是用户现场反馈，不标记为自动化测试产生的首帧回执，也不擅自把固件/型号关联的所有工具标为 passed。
2. **自动化兼容验证**：Chromium、Firefox、桌面 WebKit、手机 WebKit 共 24 项通过，覆盖 Token 分支、不生成 Token、缺少签名时失败、断开中止请求、真实 HTTP/1.1 请求体转发、旧模式退出清理、新官方表单加载/返回。使用明确的 SDK/API 替身，不是设备测试。
3. **后端检查**：`test_harness.py`、`test_live_devices.py` 与 `test_official_workspace.py` 共 41 项 pytest 通过，涵盖 Agent 运行、设备链路、官方代理及导入器；其中官方工作区 11 项覆盖新 Token 默认值、内存保存、预置账号清理和日志脱敏。产品与官方工作区的 TypeScript/Vite 构建通过；仅有现存依赖弃用警告。
4. **独立真实鉴权探针**：尝试加载本地产品模块时失败，尚未取得新 Token 的官方鉴权回执；不得把该探针记为成功。用户最新 Token 已更新到 Windows 当前用户加密凭据，未写入本文件。已运行页面/进程需重新载入凭据，不能从磁盘更新推导其内存已更新。

后续需分别留下证据：同一 Token 的 Web 与 App 并存；同一设备两个媒体会话、两台不同设备同时取流；停止后重连、设备休眠/断网恢复；同 Wi-Fi 与跨网；T8214 双摄布局与 App 调整后的 Web 画面；持续播放到设备主动断流；前台新帧进入 Cloud 并被 Agent 使用；iPhone arm64 真机桥接的控制执行。没有实测回执的项目保留“待验证”。本次只更新本地源码与 PR，未发布到云端；Windows 上未进行 Xcode 编译，iOS 本次变化仅为官方工作区的双摄说明。

## 恢复新版官方工作区

解压官方新包后执行（路径使用本机实际解压目录）：

```powershell
.venv/Scripts/python.exe scripts/import_official_web_demo.py '新版官方 Demo 目录'
.venv/Scripts/python.exe scripts/import_web_sdk.py '新版官方 Demo 目录/public/sdk'
cd Web
npm run build:official
npm run build
```

选择“Token 登录”使用最新发放的 Token。旧模式用于明确需要重新签发时；不要用重新生成 Token 作为取流失败的自动重试手段。
