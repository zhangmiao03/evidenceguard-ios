# 团队开发

本仓库包含原生 iOS、Cloud harness、Web 五栏应用、官方事件与直播接入，以及隔离测试工具。原生 iOS 仍是产品主线；独立 Web 仓库只作为历史原型参考。`main` 保存可编译的集成版本，成员在各自功能分支工作，通过 Pull Request 合并。

## 分工边界

| 目录 | 负责内容 | 共用约束 |
| --- | --- | --- |
| `EvidenceGuard/`、Xcode 工程 | SwiftUI、App SDK 桥接、TestFlight | 保留首页设计；其他页使用紧凑标题和返回 |
| `Cloud/server/evidenceguard/` | harness、工具、录像检索、试跑、设备占用 | 能力和发布检查由服务端执行 |
| `SDK/Bridge/` | Kotlin 桥接的自有改动 | 修改这里，通过 `SDK/prepare.py` 同步到本地 vendor |
| `Web/` | 助手、摄像头 Skill、任务、记忆、设置；官方直播与 SDK 切换 | 共用 Cloud API；模型密钥不进入浏览器 |
| `Cloud/fixture-lab/` | 合成画面与离线回归 | 测试标记不代表真实视觉能力 |
| `Cloud/vision-resource-lab/` | 深度、光流实验和已选结果 | 黑白图默认展示；模型用 Git LFS；输入视频及新运行输出仅本机保存 |

先改服务端 schema 与验证，再同步 Swift Codable 和 `Web/src/api.ts`。不要把一端的 UI 成功提示当成另一端已经完成操作。摄像头按 SN 生成稳定 ID，不按页面位置猜测；登记与厂商所有权验证是不同环节。

深度与光流材料从 [统一入口](Docs/VISION-RESOURCE-BENCHMARK.md) 查看。实验材料与 App / Web / Cloud 功能改动分别提交；按本次实际修改的路径暂存，提交前用 `git diff --cached --name-only` 检查范围。新实验输出默认被忽略；共享选定批次时再更新实验目录的忽略规则与结果索引。

## 拉取后运行

```bash
git clone https://github.com/zhangmiao03/evidenceguard-ios.git
cd evidenceguard-ios
git switch -c feat/你的主题
```

已有工作副本先回到 `main` 并执行 `git pull --ff-only origin main`，再创建自己的分支。当前集成版包括五栏交互、精简助手、官方事件、APNs 和同页自动保存的通知设置；build 9 已签名归档，分发状态见 [TestFlight](Docs/TESTFLIGHT.md)。通知配置见 [APNs](Docs/APNS.md)，接入与未验证能力见 [官方摄像头事件](Docs/OFFICIAL-CAMERA-EVENTS.md)，上线资源见 [服务器访问](Docs/SERVER-ACCESS.md)。

按 README 启动 Cloud 与 iOS。真实摄像头联调另外恢复官方资料包：

```bash
python3 scripts/import_sdk.py /绝对路径/工具资料包.zip
```

需编译 iOS SDK 时安装 JDK 17、Ruby 3 和 Bundler，执行：

```bash
bundle install --gemfile SDK/Gemfile
export JAVA_HOME=/你的/JDK17/Contents/Home
python3 SDK/prepare.py --check
python3 SDK/prepare.py
```

这台开发机另有本地工具目录，其他成员不需要复制该机器的路径。官方 SDK、用户凭证和私有录像由有权限的成员分别获取。不要将它们加进 Git；不要使用 `git add -f` 绕过忽略规则。

若 GitHub 的 git / codeload 下载失败，可选用已固定官方 tag 和 commit 的传输替代方式：

```bash
python3 SDK/fetch_pod_sources.py --dependency aws
python3 SDK/fetch_pod_sources.py --dependency sqlcipher
python3 SDK/fetch_pod_sources.py --dependency zip
python3 SDK/prepare.py --archive-downloads
```

它需要现有 `gh` 登录；只从各依赖的官方 GitHub 仓库取构建源文件，验证 Git blob、commit 和本地归档 SHA256，不改 CocoaPods 版本或 spec。缓存仍不入 Git。正常网络优先使用常规 CocoaPods 安装。

SDK 构建用 workspace / `EvidenceGuardSDK`，Simulator 用 project / `EvidenceGuard`。先完成框架和联调，只有用户明确要求分发后才上传 TestFlight 或添加测试组；当前可安装的是 build 8，已上传的 build 9 未分发。现场测试使用已分发的手机测试包，现场拿到摄像头与凭证后再验证 SDK。签名、HTTPS 服务和 App Store Connect 准备见 [TestFlight](Docs/TESTFLIGHT.md)。

`.env.example` 的聊天模型示例为 `doubao-seed-2-1-lite-260915`，Embedding 示例为 `doubao-embedding-vision-251215`、1024 维；图片/视频沿用豆包聊天模型，`EG_VIDEO_*` 仅用于同系列独立配置；官方原版 Demo 可选 Nova Pro 代理默认关闭，不作为生产模型或回退。实际模型标识查看 `/api/bootstrap`。修改模型、提示词和采样策略后，按版本更新视觉缓存或重建录像向量索引；不能仅保留相同维数就混用旧向量。模型 Key、服务访问令牌、APNs 私钥和私有签名配置分别由已有权限的成员配置，不随仓库复制。默认本地 `.env.example` 关闭 APNs；请使用本地或隔离测试数据运行，避免多个开发副本同时调度生产摄像头。

界面或接口变化时，同步核对 `harness/runtime.py` 的 `PRODUCT_GUIDANCE`、工具描述、返回给客户端的草案摘要、OpenAPI 字段说明和当前接入文档。提示词只描述已实现入口，不能扩大工具权限；新增界面不等于设备执行器已就绪。回归检查见 `test_prompt_contracts.py` 和 `test_web_product.py`。

`.env.example` 使用 `EG_CAMERA_SOURCE=official_sdk`，无真实设备时返回空列表。需要历史 fixture-lab 回归时，只在隔离环境显式改为 `fixture_lab`；正常手机环境不启用合成场景。官方 SDK User ID / Token 仅填写 App 的「摄像头 Skill → 连接摄像头」，不会随设备登记请求发往 Cloud。

## 提交前检查

```bash
python3 scripts/check_repository.py
Cloud/.venv/bin/python -m pytest -q
scripts/check_mobile_contracts.sh
xcodebuild -project EvidenceGuard.xcodeproj -scheme EvidenceGuard -configuration Debug -destination 'generic/platform=iOS Simulator' CODE_SIGNING_ALLOWED=NO build
```

Python 需安装 `Cloud/server/requirements.txt`，视频测试需 FFmpeg 在 PATH。Web 在 `Web/` 执行 `npm ci`、`npm test`、`npm run build`。本仓库 CI 统一执行 Cloud、Web 和不含官方 SDK 的 iOS Simulator 检查；SDK 真机编译和设备联调由持有资料包的成员在 Mac 检查。

PR 写清触发问题、改变后的行为、已运行的检查，以及未验证的设备边界。模型 Key 只放私有环境文件；Web Token 只留会话内存；App SDK Token 放 Keychain。运行数据库、模型请求记录、编译产物和 SDK 二进制均不提交。
