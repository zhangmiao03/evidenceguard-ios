# Mac 验证交接：iOS 埋点与摄像头接口回归

2026-10-16 更新：当前 `dongrunze` 已整合新版 iOS 与 SDK 宿主修复，最新验证范围和 Mac/真机步骤见 [本轮整合记录](verification/ios-branch-integration-2026-10-16.txt)。下文固定 `6ed031b` 的指令用于复现旧埋点问题，不能代替本次合并后的构建与验收。

本轮待验收源码为 `dongrunze` 的 **`6ed031b08ff7bc3838a73b3b3eaf1e5e6e1a3996`**。该提交调整了两项原生故障测试的等待逻辑，尚待 Mac 实际运行确认。GitHub Actions 因账户付款/额度限制未启动这一提交的作业，不能把它记为测试通过。

此前 `4b26b7f` 的 App 编译、3 项原有 UI 测试、3 项新增 API 测试通过，另外 2 项 API 测试超时。`6ed031b` 只调整测试等待与隔离，App 源码与 `4b26b7f` 相同。后端 207 项回归已通过，涵盖关闭/开启埋点、追踪写库失败/队列满时的采集链路，以及 Agent 直接读图和独立视觉分析。

## 1. 使用独立验证副本

在 Mac 的开发目录执行。下面的目录名必须尚不存在，避免改动队友正在开发的工程；测试脚本会给验证副本的 Xcode 工程添加测试 target。

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone --single-branch --branch dongrunze https://github.com/zhangmiao03/evidenceguard-ios.git evidenceguard-ios-verify-6ed031b
cd evidenceguard-ios-verify-6ed031b
git switch --detach 6ed031b08ff7bc3838a73b3b3eaf1e5e6e1a3996
git rev-parse HEAD
```

固定提交是为了让回传结果对应同一份源码。这里无需下载实验模型、官方 SDK、CocoaPods、模型 Key 或签名配置，也无需连接摄像头、启动后端、上传 TestFlight。使用新建模拟器和仓库默认配置；不要将私有 Release 配置复制到这个副本，本机 8790 端口也不要接生产服务隧道。

## 2. 检查工具与模拟器

需要完整 Xcode、可用的 iOS Simulator runtime、Python 3 和 Ruby 环境。脚本使用 `iPhone 16` 模拟器类型；Xcode 中应已下载支持该机型的 iOS runtime。上一轮成功编译/UI 测试的 CI 日志为 Xcode 26.6、iOS 26.5；其他环境请在回传信息中注明。

```bash
xcode-select -p
xcodebuild -version
xcrun simctl list runtimes
xcrun simctl list devicetypes
python3 --version
ruby --version
gem install --user-install xcodeproj -v 1.27.0 --no-document
ruby -rxcodeproj -e 'puts Xcodeproj::VERSION'
```

最后一行应输出 `1.27.0`。如使用队伍已有 Ruby 3/Bundler 环境，先激活对应环境，让 `ruby` 能加载这个版本。若 Xcode 要求完成首次启动、许可或组件安装，先在 Xcode 完成；若 `xcode-select` 指向 Command Line Tools，请在 Xcode 的 Settings → Locations 选择完整 Xcode 的命令行工具。当前脚本不需要开发者签名。

## 3. 保存环境、构建和测试结果

在验证副本根目录执行下面整段。由 Bash 保留流水线退出码，避免 `tee` 成功掩盖测试失败。所有输出均位于被 Git 忽略的本地目录。

```bash
bash <<'IOS_VERIFY'
set -u
set -o pipefail
ios_output="Cloud/data/ios-verification"
mkdir -p "$ios_output"
{
  date -u
  git rev-parse HEAD
  sw_vers
  uname -m
  xcode-select -p
  xcodebuild -version
  python3 --version
  ruby --version
  ruby -rxcodeproj -e 'puts Xcodeproj::VERSION'
  xcrun simctl list runtimes
} > "$ios_output/environment.txt" 2>&1

xcodebuild -project EvidenceGuard.xcodeproj -scheme EvidenceGuard \
  -configuration Debug -destination 'generic/platform=iOS Simulator' \
  CODE_SIGNING_ALLOWED=NO build 2>&1 | tee "$ios_output/build.log"
ios_build_exit=$?
printf 'build_exit=%s\n' "$ios_build_exit" > "$ios_output/exit-codes.txt"
if [ "$ios_build_exit" -ne 0 ]; then
  printf 'tests=not_run_due_to_build_failure\n' >> "$ios_output/exit-codes.txt"
  exit "$ios_build_exit"
fi

bash scripts/test_ios_compatibility.sh 2>&1 | tee "$ios_output/compatibility.log"
ios_test_exit=$?
printf 'test_exit=%s\n' "$ios_test_exit" >> "$ios_output/exit-codes.txt"
exit "$ios_test_exit"
IOS_VERIFY
```

脚本会先执行移动端契约检查，再创建模拟器并运行 3 项 UI 测试和 5 项 API 测试，结束后删除本次创建的模拟器。首次启动可能较慢，请让测试自然结束。

重复执行时，请使用新的验证副本，或者先将已有的 `CompatibilityResults.xcresult` 改名保存；`xcodebuild` 不覆盖已有结果目录。不要把脚本生成的工程修改提交回功能分支。

## 4. 判定结果

全部通过必须同时满足：

- `exit-codes.txt` 中 `build_exit=0`、`test_exit=0`。
- 构建日志出现 `BUILD SUCCEEDED`，测试日志出现 `TEST SUCCEEDED`。
- `WorkspaceTests` 的 3 项测试全部通过，`APIClientTests` 的 5 项测试全部通过，没有跳过本轮故障测试。
- 前置移动端契约检查没有失败。

重点查看以下两个上轮超时的测试，不要删除、跳过或只提高超时后宣布通过：

- `testLegacyCaptureFlowCompletesWhileObservationsAreStalled`：埋点请求挂起时，旧服务响应仍能完成开流、心跳、取帧命令、图片上传与停止。
- `testUnavailableCollectorDoesNotReplaceBusinessErrors`：埋点 404/503/超时/断网不替换原业务成功结果、409 或解码错误。

其余 API 测试检查取消语义、心跳不额外产生埋点请求、发送上限与失败后释放名额。UI 测试检查五栏可达、“我的”里的通知/官方摄像头入口、官方 SDK 检查指引的进入与返回。

## 5. 打包回传

无论成功还是失败，都保留日志。执行：

```bash
if [ -d CompatibilityResults.xcresult ]; then
  ditto CompatibilityResults.xcresult Cloud/data/ios-verification/CompatibilityResults.xcresult
fi
ditto -c -k --keepParent Cloud/data/ios-verification Cloud/data/ios-verification.zip
```

回传 `Cloud/data/ios-verification.zip`，并注明“通过 / 失败 / 环境未就绪”。压缩包应含提交号与 Xcode 环境、构建/测试日志、退出码，以及生成成功时的 `.xcresult`（可用 Xcode 打开查看截图和具体断言）。不用发送整个仓库、私有配置或 SDK 二进制。

## 6. 模拟器通过后仍需单独验收的范围

本轮 API 测试使用原生 URLSession 和真实 APIClient，URLProtocol 只替代网络响应，不包含主办方 SDK。它证明的是 App 交互及接口回归，不证明 T8171/T8214 的硬件播放已经通过。

真机后续需要分别验证：官方账号绑定与设备发现、打开实时画面和首帧、Agent 请求后取到新帧、埋点服务不可用时仍可取帧、切换官方 SDK 时释放会话、后台/锁屏停止采集及重新进入后恢复。记录机型、系统版本、SDK 版本和设备型号；这部分结果不要和模拟器结果合并成一个“全部通过”。
