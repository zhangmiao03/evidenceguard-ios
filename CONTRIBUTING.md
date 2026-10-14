# 团队开发

本仓库包含原生 iOS、Cloud harness、Web 设备工作台和模拟摄像头。本轮真实设备接入在 `dongrunze` 分支开发，Web 也放在本仓库 `Web/`；独立 Web 仓库只作为历史原型参考。`main` 为集成分支，通过团队 Review 合并。

## 分工边界

| 目录 | 负责内容 | 共用约束 |
| --- | --- | --- |
| `EvidenceGuard/`、Xcode 工程 | SwiftUI、App SDK 桥接、TestFlight | 保留首页设计；其他页使用紧凑标题和返回 |
| `Cloud/server/evidenceguard/` | harness、工具、录像检索、试跑、设备占用 | 能力和发布检查由服务端执行 |
| `SDK/Bridge/` | Kotlin 桥接的自有改动 | 修改这里，通过 `SDK/prepare.py` 同步到本地 vendor |
| `Web/` | 官方 Web 直播、设备与 Agent 工作台 | 共用 Cloud API；模型密钥不进入浏览器 |
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

已有工作副本先回到 `main` 并执行 `git pull --ff-only origin main`，再创建自己的分支。当前集成版包括五栏交互、APNs 和同页自动保存的通知设置；手机测试使用 TestFlight `1.0 (8)`。通知配置和验证边界见 [APNs](Docs/APNS.md)，上线资源见 [服务器访问](Docs/SERVER-ACCESS.md)。

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

SDK 构建用 workspace / `EvidenceGuardSDK`，Simulator 用 project / `EvidenceGuard`。本次默认通过 TestFlight 安装手机测试包，现场拿到摄像头与凭证后再验证 SDK。签名、HTTPS 服务和 App Store Connect 准备见 [TestFlight](Docs/TESTFLIGHT.md)。

聊天、视觉和工具调用统一使用 `doubao-seed-2-1-lite-260915`；Embedding 使用 `doubao-embedding-vision-251215`、1024 维。模型 Key、服务访问令牌、APNs 私钥和私有签名配置分别由已有权限的成员配置，不随仓库复制。默认本地 `.env.example` 关闭 APNs；请使用本地或隔离测试数据运行，避免多个开发副本同时调度生产摄像头。

## 提交前检查

```bash
python3 scripts/check_repository.py
Cloud/.venv/bin/python -m pytest -q
scripts/check_mobile_contracts.sh
xcodebuild -project EvidenceGuard.xcodeproj -scheme EvidenceGuard -configuration Debug -destination 'generic/platform=iOS Simulator' CODE_SIGNING_ALLOWED=NO build
```

Python 需安装 `Cloud/server/requirements.txt`，视频测试需 FFmpeg 在 PATH。Web 在 `Web/` 执行 `npm ci`、`npm test`、`npm run build`。本仓库 CI 统一执行 Cloud、Web 和不含官方 SDK 的 iOS Simulator 检查；SDK 真机编译和设备联调由持有资料包的成员在 Mac 检查。

PR 写清触发问题、改变后的行为、已运行的检查，以及未验证的设备边界。模型 Key 只放私有环境文件；Web Token 只留会话内存；App SDK Token 放 Keychain。运行数据库、模型请求记录、编译产物和 SDK 二进制均不提交。
