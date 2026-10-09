# 团队开发

本仓库包含原生 iOS、Cloud harness 和模拟摄像头。Web 原型在 [独立仓库](https://github.com/zhangmiao03/evidenceguard-web)，当前暂缓开发。`main` 保存可编译的集成版本；每个成员在 `feat/主题` 或 `fix/主题` 分支工作，通过 Pull Request 合并。

## 分工边界

| 目录 | 负责内容 | 共用约束 |
| --- | --- | --- |
| `EvidenceGuard/`、Xcode 工程 | SwiftUI、App SDK 桥接、TestFlight | 保留首页设计；其他页使用紧凑标题和返回 |
| `Cloud/server/evidenceguard/` | harness、工具、录像检索、试跑、设备占用 | 能力和发布检查由服务端执行 |
| `SDK/Bridge/` | Kotlin 桥接的自有改动 | 修改这里，通过 `SDK/prepare.py` 同步到本地 vendor |
| `Cloud/fixture-lab/` | 合成画面与离线回归 | 测试标记不代表真实视觉能力 |

先改服务端 schema 与验证，再同步 Swift Codable；后续恢复 Web 开发时再更新 Web 仓库的 types.ts。不要把一端的 UI 成功提示当成另一端已经完成操作。摄像头 SN 与逻辑设备 ID 的映射需要验证，不按页面位置猜测。

## 拉取后运行

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

## 提交前检查

```bash
python -m pytest -q
xcodebuild -project EvidenceGuard.xcodeproj -scheme EvidenceGuard -configuration Debug -destination 'generic/platform=iOS Simulator' CODE_SIGNING_ALLOWED=NO build
```

Python 需安装 `Cloud/server/requirements.txt`，视频测试需 FFmpeg 在 PATH。本仓库 CI 执行 Cloud 和不含官方 SDK 的 iOS Simulator 检查；Web 检查由 Web 仓库独立执行；SDK 真机编译和设备联调由持有资料包的成员在本机检查。

PR 写清触发问题、改变后的行为、已运行的检查，以及未验证的设备边界。模型 Key 只放私有环境文件；Web Token 只留会话内存；App SDK Token 放 Keychain。运行数据库、模型请求记录、编译产物和 SDK 二进制均不提交。
