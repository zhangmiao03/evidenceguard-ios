# 团队开发

仓库同时包含 Web、原生 iOS、Cloud harness 和模拟摄像头。`main` 保存可编译的集成版本；每个成员在 `feat/主题` 或 `fix/主题` 分支工作，通过 Pull Request 合并。

## 分工边界

| 目录 | 负责内容 | 共用约束 |
| --- | --- | --- |
| `Web/` | React 界面、圈选、录像播放、Web SDK 联调 | 调用 `/api`，不自行决定 Skill 可执行性 |
| `EvidenceGuard/`、Xcode 工程 | SwiftUI、App SDK 桥接、TestFlight | 保留首页设计；其他页使用紧凑标题和返回 |
| `Cloud/server/evidenceguard/` | harness、工具、录像检索、试跑、设备占用 | 能力和发布检查由服务端执行 |
| `SDK/Bridge/` | Kotlin 桥接的自有改动 | 修改这里，通过 `SDK/prepare.py` 同步到本地 vendor |
| `Cloud/fixture-lab/` | 合成画面与离线回归 | 测试标记不代表真实视觉能力 |

先改服务端 schema 与验证，再同步 Web 和 Swift Codable。不要把一端的 UI 成功提示当成另一端已经完成操作。摄像头 SN 与逻辑设备 ID 的映射需要验证，不按页面位置猜测。

## 拉取后运行

按 README 启动 Cloud 与 Web。真实摄像头联调另外恢复官方资料包：

```bash
python3 scripts/import_sdk.py /绝对路径/工具资料包.zip --web-only
```

需编译 iOS SDK 时移除 `--web-only`，安装 JDK 17、Ruby 3 和 Bundler，执行：

```bash
bundle install --gemfile SDK/Gemfile
export JAVA_HOME=/你的/JDK17/Contents/Home
python3 SDK/prepare.py --check
python3 SDK/prepare.py
```

这台开发机另有本地工具目录，其他成员不需要复制该机器的路径。官方 SDK、用户凭证和私有录像由有权限的成员分别获取。不要将它们加进 Git；不要使用 `git add -f` 绕过忽略规则。

## 提交前检查

```bash
npm --prefix Web ci
npm --prefix Web test
npm --prefix Web run build
python -m pytest -q
xcodebuild -project EvidenceGuard.xcodeproj -scheme EvidenceGuard -configuration Debug -destination 'generic/platform=iOS Simulator' CODE_SIGNING_ALLOWED=NO build
```

Python 需安装 `Cloud/server/requirements.txt`，视频测试需 FFmpeg 在 PATH。CI 执行 Web、Cloud 和不含官方 SDK 的 iOS Simulator 检查；SDK 真机编译和设备联调由持有资料包的成员在本机检查。

PR 写清触发问题、改变后的行为、已运行的检查，以及未验证的设备边界。模型 Key 只放私有环境文件；Web Token 只留会话内存；App SDK Token 放 Keychain。运行数据库、模型请求记录、编译产物和 SDK 二进制均不提交。
