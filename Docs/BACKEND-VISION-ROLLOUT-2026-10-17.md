# 后端图像处理与单步控制接入

本轮只修改 Cloud、后端发布工具和测试。iOS、Kotlin 桥接及 Web 前端源码不修改。开发基线为 `dongrunze@ff67482`；发布前再次核对实际服务路径、源码哈希及私有配置哈希。云端现用视觉提供方为火山 Ark，模型 `doubao-seed-2-1-lite-260915`；使用服务器当前配置完成小型合成图片请求，HTTP 200。没有从本机恢复旧密钥，也没有把密钥写进仓库或报告。

## 四项工作的真实状态

| 工作 | 本轮后端实现 | 仍需客户端或真机的部分 |
|---|---|---|
| 新帧与帧窗口 | 保存现有上传接口接收的真实样本；每设备最多12张、最多30秒、总内存窗口64MB；显式请求两次取样 | 后端无法生成 iOS 解码回调。HTTP sequence 不是解码帧号；现有 `camera_observe.ready=false` 保留 |
| 深度与光流 | CPU 子进程运行 DepthART448 与 DIS；权重SHA校验、单并发、队列与超时；实际辅助图片进入模型 | 光流需同设备/会话/视角、间隔≤1秒；现有客户端不能保证达到此速率，未满足时明确跳过 |
| 分析到工具 | 新的目标定位器返回当前全图目标框，后端计算一次居中方向，交现有 `camera_ptz_step` | 需要 T8171、有效原生观察引用、本平台设备验收、暂停固定区域守护，并使用现有操作确认卡 |
| 动作后复核 | SDK回执后再取新图、重新定位，比较中心偏移；未知/超时不重发，不追加第二步 | 尚未取得本轮 iOS 电机真机验收；图像变好不等于机械停止证明，人工效果字段不自动改成已确认 |

因此，这次能部署完整的后端处理及编排，但不能宣称仅后端改动就补出了缺失的原生帧凭据。当前仓库 `SDK/Bridge/Tools/HardwareToolJson.kt` 将 `camera_observe.ready` 声明为 false；按此版本注册时会返回 `NATIVE_DECODER_PROOF_REQUIRED`。线上保留的旧设备登记不能代替新版本验收；也不能把 ready 改成 true 绕过帧凭据校验。官方 SDK 能力与产品执行器接入状态是两件事。

## 三种分析入口

1. 已开启的守护：沿用参考图/当前图及ROI，启用 `EG_GUARD_AUX_ENABLED` 后附加实际深度和合格的光流诊断，再交原有 SceneHarness 判定。辅助失败会标明不可用，RGB守护仍可继续；原有配额保留。
2. `analyze_visual_endpoints`：读取已存参考/最近采样。默认保持RGB兼容；`include_depth=true` 请求实际DepthART，两张RGB+两个裁剪+两张深度，标识为条件C。分析缓存包含处理版本、模式和辅助帧引用。深度失败不伪装成功。
3. `sample_camera_vision`：经既有取图链路发出两次真实挑战，总采样上限12秒；用用户参考图与最后一张比较，以新采样的短间隔对计算光流。不能通过插值、重编号或上传时间伪造相邻帧。此入口不改守护状态，也不移动设备。

DIS输出包括前后向一致性、SIFT几何匹配、稠密/稀疏差异和像素位移诊断；质量不足不提供可用箭头图。相机背景平移候选不是相机姿态。DepthART每帧独立p2–p98归一化，近亮远暗，不提供米制距离，也不跨帧比较灰度判断远近。T8214当前SDK画面不能被解释成已标定的两路独立镜头。

CPU处理器同一时刻最多一个子进程，最多3个待处理请求，排队8秒，处理25秒；超时杀掉子进程并释放名额。模型API使用当前显式提供方，未设置旧密钥/旧服务自动重试。DepthART权重路径来自服务端部署配置，模型不能传路径或下载地址。

## 控制链路与旧 App 兼容

```text
用户明确要求把已框选目标调到中央
 → aim_camera_at_guard_target(guard_id, revision)
 → 私有归属/本轮设备/原生执行器/硬件验收/守护占用检查
 → camera_observe 获得真实解码引用
 → RGB + 可用辅助图 → 独立定位提示词 → 当前目标框
 → 程序计算一次方向单步 → 既有 iOS 操作卡确认
 → iOS 执行器 → 官方 SDK → 回执
 → 新观察 + 重新定位 → 中心偏移变化 / 无法确认
```

目标框不明确、遮挡或对应不清不生成动作。中心±0.12归一化范围内不移动；超出时只选择偏移更大的一个轴。这里是单步图像居中方案，不承诺角度、速度、持续追踪或绝对空间位置。镜像配置及实际轴向仍需真机验收；一次动作后的偏移如果恶化，不自动反向补偿。

动作使用原来的工具名和回执格式，Agent运行结果继续写入 `hardwareOperations`，因此现有确认卡可用。新增 `visualControlId` 及只读复核字段均为附加字段。取消、过期引用、固件/能力修订变化、未知停止状态仍由原工具运行时拦截。重启将未完成视觉编排标为 interrupted，不重放旧电机命令。

T8214返回 `NO_MECHANICAL_PTZ`；门铃双摄模式仍走独立官方工具，不通过视觉居中接口模拟云台。

## 接口、配置与定位

| 接口/工具 | 作用 |
|---|---|
| `GET /api/vision/status` | 当前模型配置、实际本地依赖/权重校验、每设备控制缺口；要求团队令牌+安装身份+私有空间凭据 |
| `POST /api/visual-scenes/{id}/sample-analysis` | `{revision}`，本人已框选场景的新采样及深度/光流分析 |
| `POST /api/visual-scenes/{id}/analyze` | 保留 `{revision,includeDepth}` 兼容 |
| `GET /api/vision/controls/{id}` | 本人的单步编排及后续复核，其他安装实例不可读取 |
| `sample_camera_vision` | 助手显式短时取样分析 |
| `aim_camera_at_guard_target` | 创建一次现有硬件操作卡，前置条件不满足则返回blocked |
| `read_visual_control` | 查询编排结果，不追加动作 |

新增助手工具只在已有私有认证的新版 iOS 实时守护上下文出现，历史检索不授予它们。私人图像分析、定位与相关回复不进入公共Dashboard正文；固定提示词、哈希及运行元数据可检查。业务媒体仍沿用既有团队访问策略，未重新设计整个媒体权限系统。

显式部署设置：`EG_ENDPOINT_ENABLED=1`、`EG_ENDPOINT_PROFILE=video`、`EG_LOCAL_VISION_ENABLED=1`、`EG_FLOW_ENABLED=1`、`EG_GUARD_AUX_ENABLED=1`、`EG_VISUAL_CONTROL_ENABLED=1`、`EG_DEPTH_MODEL_PATH=<已校验权重>`。专用模型模式 `dedicated` 仍支持独立 `EG_ENDPOINT_BASE_URL/MODEL_ID/API_KEY`。这次选择 `video` 以复用云端刚更新的有效配置；配置缺失或调用失败时不回退官方旧额度。

源码：`vision/processing.py` / `worker.py` / `endpoints.py` / `control.py`；`camera/live.py`；`visual_skills/{harness,service,chat,routes}.py`；`hardware_tools/gateway.py`。部署工具为 `Cloud/demo_release/{capture_runtime,package_runtime,runtime_release,vision_assets}.py`。

## 验证与发布记录

本机最终合并执行后端、Dashboard及发布工具测试：541通过、10项POSIX跳过（64.34秒）。包含真实深度图输入、现有Agent确认卡、历史工具隔离、会话/视角变化丢弃及分辨率变化拒绝等检查。CPU测试使用真实ONNX/DIS和合成像素；控制测试使用明确标记的执行器替身，不称为真机测试。Linux独立发布环境的检查结果见下表。

发布采用release内独立venv和源码目录，保留Web静态资源及 `/etc/evidenceguard-demo/cloud.env` 原文件。激活前再次核对源码/配置漂移，拒绝中断活跃Agent、检索、索引及未解决硬件动作；失败恢复前一运行版本。回滚只切代码及本次非秘密功能开关，不恢复旧业务数据库、不覆盖新密钥。

已于 **2026-10-17 04:05 新加坡时间**切换并验收 demo：

| 项目 | 结果 |
|---|---|
| 源码提交 | `a9387d2`，后续文档提交不改变该运行源码 |
| 发布目录 | `/opt/evidenceguard-demo/releases/tools-e4725de3d0d287d8` |
| 内容哈希 | `88045bba6984ca6edd92dc64bb67a084c47ee6aad5bd240f55fbf0f5f3c86daa` |
| 回滚目录 | `/var/backups/evidenceguard-demo-tools/20261016T200539086460Z` |
| Linux 后端 | 482通过、1跳过，110.97秒；跳过项依赖仓库内LFS权重路径，部署使用独立模型目录，已另做真实运算测试 |
| 实际 CPU 运算 | DepthART448两张深度图 + DIS箭头图；两次合成图预处理分别557ms、743ms；人为3px横移测得背景候选约2.965px，只是算法烟测 |
| 最新密钥与模型 | 更新后的云端私有配置真实图片请求HTTP 200；两次完整首尾图分析中一次因连续跟踪字段不合规被拒绝，一次条件C通过；不伪造/自动修正该字段，不自动换回旧密钥 |
| 线上接口 | 公网health 200；无团队身份的bootstrap/vision状态401；有团队身份但无私有凭据403；私有状态200，depthReady/flowReady均true |
| 现有 App 兼容 | 原bootstrap 200；旧Observer兼容检查通过；私有目标定位与首尾分析提示词均进入运行时Catalog |
| 数据与其他服务 | 4项Skill、170媒体、22证据、100运行、2录像及个人表计数保持；数据库quick_check通过；密钥文件哈希、Web静态资源哈希、team/review进程均不变 |
| 真机状态 | 未发出设备动作。线上两个已登记执行器离线，存在未通过验收和守护占用；设备记录不能证明原生解码能力已接通 |

烟测的合成图片只存在于独立临时数据库；私有接口使用一次性测试身份，检查后删除该身份自己的凭据绑定。没有向公开仓库提交业务图片、密钥或私有配置。

保持 AWS 已登录后，可在仓库根目录执行代码回滚：

```powershell
python scripts/cloud_command.py --command '/opt/evidenceguard-demo/releases/tools-e4725de3d0d287d8/venv/bin/python /opt/evidenceguard-demo/releases/tools-e4725de3d0d287d8/runtime_release.py --rollback /var/backups/evidenceguard-demo-tools/20261016T200539086460Z' --timeout 120
```

回滚指向前一 `tools-4253361ffd4635a4` 运行版本；保留发布后的业务写入及当前私有密钥。若期间已有其他人发布新版，回滚工具会拒绝覆盖，须先重新比对当前状态。回滚流程有自动化检查和真实备份；本次没有为演示回滚再中断一次已恢复的服务。

现有App可用的联调路径：打开设备直播，在摄像头守护里框选并保存目标；实时助手明确请求“为这个守护取新图并用深度分析”，由 `sample_camera_vision` 复用原上传接口。原有“对照参考图”按钮保持RGB默认，助手 `analyze_visual_endpoints(include_depth=true)` 或私有HTTP接口可显式选择深度。光流间隔不满足时返回跳过原因。云台居中请求会先返回当前能力缺口；只有原生解码来源、真实硬件验收和守护暂停均满足后，才会生成旧App已有的确认卡。
