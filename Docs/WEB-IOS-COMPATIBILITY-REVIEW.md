# Web / iOS 新增源码复审与兼容性验收

日期：2026-10-14。分支：`dongrunze`。审核基线：`b75f9b1630fe05bc9a0f07984d831c0312e298de`。

## 最新主分支同步

本次已将远端 `main` 的 `0959463` 合入 `dongrunze`，处理下方记录的 8 个冲突文件。保留 main 的五栏界面、APNs、提醒偏好自动保存，以及本分支的 iOS / Web 实时采集和官方工作区。

- AppDelegate 合并为一个 `PushAppDelegate`，同时实现 APNs 回调和官方播放器方向控制。
- 推送注册与前台状态维护放在持续存在的工作区外壳。官方页面、切换期间、后台或弹窗占用界面时保留通知点击；返回释放完成后只路由一次，保留助手、任务、记忆导航。
- APIClient 同时保留 `X-EG-Push-Key` 与 `X-EG-Media-Session`，各自只用于对应请求。新增 HTTP 联合回归，核对关闭推送不停止直播、停止直播不关闭推送，且两种凭证不能互相授权。
- 普通与 SDK 两个 Xcode 目标均保留 LiveCameraView、PushNotifications、ReminderSettings 和推送 entitlement；官方账号入口在内部演示配置也可访问。
- 环境示例、忽略规则、仓库扫描同时保留 APNs 私钥与官方 Demo 的保护条目。Web 保持设备工作台定位，与合并后的 Cloud 共用实时接口。

合并提交与受测代码为 `60ca5140b7b9d157d421f949e569bcec483c3523`，两位父提交分别为 `215c1f8` 和 `0959463`。[合并后 GitHub Checks 四项全部成功](https://github.com/zhangmiao03/evidenceguard-ios/actions/runs/38546350635)，完成于 2026-10-14 18:03（UTC+8）。结束前再次 fetch，远端 main 仍为 `0959463`。

| 合并后检查 | 结果 |
| --- | --- |
| Cloud | 本地与 Linux CI 均为 **179 通过** |
| Web 协议 / 构建 | **4 通过**；TypeScript 与生产构建通过 |
| Linux 多浏览器 | **48 通过、4 跳过** |
| macOS WebKit / 手机尺寸 | **24 通过、2 跳过** |
| 原生 iOS | 普通目标编译通过，**3 项 XCUITest 通过**，操作新的五栏、SDK 指引及“我的”中的通知 / 官方摄像头入口 |
| Swift 契约 | 原有服务迁移、聊天持久化、提醒自动保存，加上新增延期推送导航均通过 |
| 仓库扫描 | **359 个文件通过**；无未解决冲突及禁止提交的本地文件 |

CI 的 6 项浏览器跳过均为未放入官方 Demo 文件的检查。新增推送导航测试验证真实业务导航函数：官方工作区、释放过程、弹窗和冷启动期间保留点击，恢复后只路由一次并保留其他标签导航。原版 SDK 的实际释放与 APNs 真机点击组合仍需硬件确认。本轮没有发布线上服务或 TestFlight；下方旧测试结果属于合并前代码。

## 合并前验收记录

修复后验收代码：`f4db02e66cea45ee59507523f452b19798ad6b7c`。[GitHub Checks 四个任务全部成功](https://github.com/zhangmiao03/evidenceguard-ios/actions/runs/38544089264)，测试完成时间为 2026-10-14 17:44（UTC+8）。本报告与 README 的后续提交只补充验收结果，不改变受测代码。

## 结论与范围

本轮重新阅读 Web 工作台、官方 Demo 外壳、SwiftUI 直播页、Kotlin 桥接、采集 API 和 Agent 图片输入代码，修复生命周期及浏览器兼容问题，并加入可重复运行的浏览器和原生 UI 测试。

本地通过的是软件协议、界面和对合成视频的读取。**尚不能宣布 T8171 / T8214 实机直播、绑定、对讲或本轮官方 iOS arm64 桥接通过。** 赛事账号、硬件和持有官方库的 Mac 仍需单独验收。本轮没有更新线上服务或 TestFlight。

## 已发现并修复

| 优先级 | 原问题与影响 | 修复及验证 |
| --- | --- | --- |
| P1 | Web 退出先清团队令牌，稍后的停止请求缺少鉴权；快速重连先于旧租约释放 | 关闭、换设备、退出、切工作区共用异步结束流程；等停止回执和 SDK 释放，再清凭证或开新会话。浏览器复现后回归通过 |
| P1 | iOS 重连与未完成的 start/原生释放交叠；页面取消可能丢失晚到的开流回执 | 开流互斥、重连等待释放；晚到的开流回执主动停止；清理任务不随页面取消，保留原生释放余量 |
| P1 | iOS 离页只取消本地轮询，云端 Agent 继续运行；Web 晚到的 run 也可能继续运行 | 问题代次、服务端取消和晚到回执处理。Web 延迟 start 回归通过；iOS 真实 SDK 路径待真机 |
| P2 | 等待新帧时心跳新鲜度过期；iOS 将取消取图的 409 当直播故障 | 上传前刷新新样本心跳；iOS 识别 409，下一次心跳检查会话有效性 |
| P2 | 浏览器拒绝 localStorage 时白屏；缺少 UUID/timeout 便捷 API 时阻断 | 存储失败改为本页身份，UUID 用安全随机数兼容路径，请求超时用 AbortController |
| P2 | 普通局域网 HTTP 下直接报错或缺少凭证传输限制 | 页面可打开并提示 HTTPS；发送凭证前检查来源。测试确认没有发出 API 凭证请求 |
| P2 | SDK 异步报告裸帧不支持时没有降级；无逐帧 API 只能长时间等待 | 尝试实际 video 帧回调；两条路径均不可用时明确停止，不使用 UI 截屏或历史封面 |
| P2 | 手机布局隐藏退出入口；WebKit 关闭设置后焦点丢失 | 增加手机退出按钮，显式恢复触发控件焦点；跨浏览器回归通过 |

主要修改：`Web/src/App.tsx`、`LiveView.tsx`、`browser-support.ts`、`api.ts`、`OfficialWorkspace.tsx`、`EvidenceGuard/LiveCameraView.swift`、`APIClient.swift`。

## Windows 本地实测

环境：Node 24.13.1、Python 3.12.14、Playwright 1.58.2；CI 使用 Node 22 / Python 3.12。

| 浏览器 | 版本 | 结果 | 实际覆盖 |
| --- | --- | --- | --- |
| Chromium | 145.0.7632.6 | 13 通过 | 界面/会话、合成 H.264 视频与 JPEG、两种裸帧失败降级 |
| Google Chrome | 155.0.8059.79 | 13 通过 | 同上；本机 Chrome 程序 |
| Microsoft Edge | 155.0.4283.45 | 13 通过 | 同上；本机 Edge 程序 |
| Firefox（Playwright 版） | 146.0.1 | 13 通过 | 同上 |
| WebKit（Windows） | 26.0 | 11 通过、2 跳过 | 缺少 requestVideoFrameCallback，跳过降级取样；拒绝旧图并提示不支持通过 |
| 手机尺寸 WebKit（iPhone 13 配置） | 26.0 | 11 通过、2 跳过 | 手机布局/操作模拟，不是 iPhone 真机；逐帧边界同上一行 |

合计 **74 通过、4 跳过、0 失败**。完整报告 `Web/playwright-report/index.html`、截图和 trace 均在被 Git 忽略的输出目录。

13 类用例：禁用存储、弹窗布局/焦点、带原凭证退出、迟到开流后的工作区切换、立即重连、缺少便利 API、HTTP 限制、两种 video 降级、无取帧 API 的明确失败、离开前台、迟到 Agent 取消、原版 Demo 加载/返回。

业务流程测试明确替换厂商 SDK 和 API 响应；视频由 FFmpeg 合成。最后一项使用本机恢复的**真实官方 UMD 和原始表单**，只检查加载与返回，没有登录账号。官方文件不进入 Git，该项在 CI 明确跳过。

不同系统上的 WebKit 功能/媒体支持有差异，Windows 结果不能代替 Safari；见 [Playwright 官方说明](https://playwright.dev/docs/browsers#webkit)。因此另加 macOS WebKit 测试。

## 后端及构建

- Linux CI 多浏览器：**48 通过、4 跳过、0 失败**，覆盖 Chromium、Firefox、WebKit 和手机尺寸 WebKit。4 项跳过都是未分发到 CI 的原版 Demo 加载检查；两类 video 回退在四个配置均通过。
- 后端 **163 项通过**：设备身份、账号冲突、会话归属、旧帧/错误设备拒绝、停止与过期、HTTP 取图全流程、Agent 两条视觉输入、代理访问边界。
- Web **4 项协议单测通过**；TypeScript、自有生产构建、恢复后的官方 Demo 构建通过。
- npm 审计：0 高危/中危，1 项 low，来自官方对照页的 `elliptic 6.6.1`，暂无直接修复版本。自有握手使用 WebCrypto。外部官方 UMD 不属于 npm 审计范围。
- 测试脚本模型的回答不等同真实模型理解；没有将 `physicalDevicesValidated` 改为 true。

## Apple 平台自动化

本轮 CI 新增以下检查，执行记录见 [兼容性检查](https://github.com/zhangmiao03/evidenceguard-ios/actions/runs/38544089264)：

1. 普通 `EvidenceGuard` iOS Simulator 编译。
2. Swift 服务地址、聊天迁移、二维码、聊天持久化契约测试。
3. 启动 iOS Simulator，XCUITest 操作五个原生标签页，打开 SDK 检查指引并返回；截图存入 xcresult。
4. macOS WebKit / 手机尺寸 WebKit 执行同套 Web 测试。

原生实测环境为 macOS 26.6.2 / Xcode 26.6 / iPhone 16 Simulator（iOS 26.5）。普通 App 编译通过，Swift 契约检查通过，**2 项 XCUITest 全部通过**：逐个点击五个真实 SwiftUI 标签页，检查 SDK 入口；打开模拟器中的官方检查指引，核对限制提示并返回。测试操作的是原生编译后的界面。

Simulator 不编译 `#if canImport(SampleCore) && !targetEnvironment(simulator)` 内的官方路径，不能替代 `EvidenceGuardSDK` arm64 构建和设备测试。

macOS WebKit 两个配置共 **24 通过、2 跳过**；两项跳过均因 CI 未放入主办方原版 Demo。桌面和手机尺寸的两类 video 回退均通过，包含浏览器实际解码合成 H.264 视频并产生 JPEG。这仍不是 iPhone Safari 真机结果。

首轮新增测试出现了两个测试环境问题，并保留了失败记录：生成的 XCUITest target 没有 PRODUCT_NAME，普通 App 编译通过而测试包路径冲突；Linux WebKit 在加载和填表阶段耗尽 30 秒总时限，退出断言开始时只余约 0.5 秒。已补齐测试 target 名称，将 CI 并发改为 2、整例上限改为 60 秒，业务断言时限未放宽、未添加自动重试。

工程最低部署目标为 iOS 17，当前 CI 使用已安装的最新可用 runtime。通过当前 runtime 不等于逐个验收所有 iOS 17 及以上版本；最低版本、真实 iPhone、厂商 arm64 和签名 Archive 仍应在发布前验证。

## 复现

```powershell
# Windows，仓库根目录
.\.venv\Scripts\python.exe -m pytest -q
cd Web
npm ci
npx playwright install chromium firefox webkit
npm test
npm run build
# ffmpeg 须在 PATH；安装了 Chrome/Edge 时也加入它们
$env:EG_BRANDED_BROWSERS = '1'
npm run test:browser
```

```bash
# Mac，仓库根目录；普通原生 UI 无需赛事库
gem install xcodeproj -v 1.27.0 --no-document
bash scripts/test_ios_compatibility.sh
```

原生脚本在本地工程生成 EvidenceGuardReview 测试方案，使用已安装的 iOS Runtime 创建专用 iPhone 16 模拟器，测试后删除该专用模拟器。生成的测试工程变更无需提交到业务分支。结果用 `open CompatibilityResults.xcresult` 查看；Web 用 `npx playwright show-report`。

## 仍需硬件验收的发布门槛

| 环节 | 通过标准 |
| --- | --- |
| 本轮原生桥接 | Mac 恢复资料、重新执行 SDK/prepare.py；EvidenceGuardSDK 完成 arm64 Debug/Archive，不复用旧 SampleCore |
| 双型号 | T8171/T8214 各自登录、枚举、同步、首帧、停止、重连；现场物体改变后 Agent 得到对应新图 |
| 跨端 | 同 SN 同设备 ID；停旧采集端后另一端接管；另一客户端可向前台采集端请求新图 |
| 生命周期 | 开流未返回时切官方；立即重连；取图/Agent 中离页、锁屏、断网；恢复后不能返回旧图成功回执 |
| 官方工作区 | iOS 原版绑定、配网、对讲、PTZ、录像、回放/下载后返回；资源释放，账号/PR/QA 不混用 |
| Safari 真机 | HTTPS 下官方 SDK 解码、实际画面读取、麦克风、前后台与旋转 |
| 视觉模型 | 使用真实模型核对来源、描述和遮挡不确定性，不用脚本回答代替 |

当前仍为单团队、单后端进程、前台取样。成员权限、独立归属核验、后台采集、完整 Web 配网/设置产品流程不属于本轮。官方页面存在与设备实际支持分别记录。

## 合并前发现的主分支差异（上述同步已处理）

审核过程中远端 `main` 从 `1bf084e` 更新到 `0959463`（个人 Agent 五标签与 APNs 合并）。本轮修复提交 `2fec234` 仍位于 `dongrunze`。对两个真实 Git 树执行 `git merge-tree --write-tree --name-only HEAD origin/main`，**存在 8 个冲突文件，不能将本分支通过解释为已与最新 main 完成兼容**：

`.env.example`、`EvidenceGuard.xcodeproj/project.pbxproj`、`EvidenceGuard/APIClient.swift`、`EvidenceGuard/EvidenceGuardApp.swift`、`EvidenceGuard/ProfileView.swift`、`EvidenceGuard/RootView.swift`、`README.md`、`scripts/check_repository.py`。

读源后的合并要求：

- AppDelegate 必须同时处理 APNs 回调与官方播放器方向控制，不能只保留两个 delegate 之一或机械添加两个入口。
- RootView 要保留官方工作区外壳，并接入新的 AppTab 枚举、推送路由和前台 presence；返回产品模式不能继续假定 selectedTab 是整数。UI 测试也要随新五标签文案更新。
- APIClient.send 必须同时保留 `push` 与 `mediaSession` 参数、推送密钥头和采集会话头。
- Xcode 工程同时保留 LiveCameraView、PushNotifications、ReminderSettings 和推送 entitlements；环境示例、忽略规则与仓库检查合并两边新增条目。

这段记录对应首次复审时不改工作区的合并预检。用户随后要求同步主分支，处理与重新验证情况见本文最上方“最新主分支同步”。
