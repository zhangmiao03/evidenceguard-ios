# EvidenceGuard Web

> **开发范围更新（2026-10-16）：** 团队已决定将比赛演示集中到原生 iOS + 官方 App SDK + Cloud Agent。产品 Web 停止功能扩展和与 iOS 的功能对齐验收；下文记录已有实现，不代表继续开发 Web 硬件演示。现有源码、官方 Demo 与已部署入口保留，Dashboard 继续作为团队观察与排查工具。此次决定不删除代码或下线服务，详见[仓库当前演示路线](../README.md#当前演示路线2026-10-16)。

Web 0.2（React 18 + TypeScript + Vite），与新版 iOS 共用 Cloud，提供 **助手 / 摄像头 Skill / 任务 / 记忆 / 设置** 五个功能区。桌面使用侧栏，手机使用底部导航；保留官方直播、按请求获取新画面与官方 SDK 工作区切换。

2026-10-16 已接入官方 `web-sdk-hackathon-demo-1016-1411.zip` 的直接 Token 登录流程。产品“接入设备”默认选择“赛事 Token 直连（PR / US）”，填写 User ID、Token 和官方示例的 App Name / Client ID / Preset Key，不调用 `request_token`。旧的 account_uuid 换取流程仍保留并明确提示会刷新 Token。官方工作区也恢复为这份新版 Demo，保留两种登录方式；Token 不进入浏览器持久存储、页面日志或 Git。

**硬件边界：用户于 2026-10-16 手动确认 Web 取流正常；Web 自制左右按钮不能直接控制 T8171 云台。** 当前两款设备的 Web SDK 只提供 Live 媒体路线。控制须由 iOS/Android 原生 App SDK 执行；本项目 Web 通过 `/api/hardware/*` 委派前台 iOS，仍需实际 SDK 回执与真机验证。T8214 门铃没有云台。不能把网页布局、SDK 的同名导出方法或 Token 共用等同于控制能力或多端同时取流通过。

T8214 的前向广角主摄关注门口与来访者，下视摄像头关注门槛与包裹。官方文档明确 Web 接收设备端合成的一路视频，App 调整拼接方式后 Web 随之切换；产品 `channelId=main` 表示逻辑输入，不代表只采前向主摄。Agent 按实际画面区分视角，不预设布局或将重叠目标重复计数。

新版包的 UMD 与原交付逐字节一致，改变的是 Demo 的鉴权逻辑；完整比较、验收范围和当前待测项见 [10 月 16 日接入记录](../Docs/SDK-TOKEN-AND-HARDWARE-BOUNDARIES-2026-10-16.md)。本节是本地源码状态，线上部署以发布记录为准。

2026-10-15 工具链更新：摄像头页合并 `/api/devices` 与 bootstrap 的事件设备，不为仅事件设备虚构直播 SN；新增 `/api/sdk/events` 时间线、缺图/核验/录像标记。硬件工具面板与助手操作卡接 `/api/hardware/*`，可向前台 iOS 委派有限 SDK 控制；Web 自身只登记观察执行器，复用当前播放器。确认、结果未知时人工核对及显式执行端交接均在页面可操作。

Web 工具观察的隐私状态默认 unknown，仅当前直播宿主可以在核对官方设置后授权 5 分钟人工诊断，不自动开放 Agent 权限。原有 `request_camera_snapshot` 实时画面能力不变。官方模式切换会先结束工具领取、媒体会话与订阅。完整接口和验收边界见 [硬件工具接入说明](../Docs/HARDWARE-TOOLS-INTEGRATION.md)，无需启动包内独立 v2 测试服务。

| 功能区 | 已实现的业务流程 |
| --- | --- |
| 助手 | 无设备也可聊任务；主会话、独立话题、重命名、草稿恢复；现场 / 只读历史两种范围、日期过滤；主动提醒依据与反馈；草案、截图和录像结果入口 |
| 摄像头 Skill | 已绑定设备导入、设备选择、前台直播、单图取样；圈选目标和各视角区域；录像上传、播放和检索索引 |
| 任务 | 按状态 / 需要关注筛选；三步草案编辑、能力检查、回放试跑与人工验收；暂停、恢复、停止、复核；设备占用确认、运行记录、证据和每日概况 |
| 记忆 | 添加并确认长期 / 24 小时记忆、筛选、移除确认；过期内容不参与后续对话 |
| 设置 | 主动提醒、每日概况时间、时区、免打扰、提醒记录；连接状态、官方账号、官方 SDK 入口、隐私与使用说明 |

后端新增 `POST /api/agent/conversations/main`，按当前客户端幂等恢复主会话；请同时更新 Cloud 和 Web。其余流程复用现有 iOS 接口与服务端能力门禁。实现说明、数据范围和检查步骤见 [Web 功能对齐](../Docs/WEB-PRODUCT-PARITY.md)。

需要 Node.js 22+。先在仓库根目录恢复有权使用的主办方 SDK：

```bash
python3 scripts/import_web_sdk.py "/绝对路径/WebSDKDemo/public/sdk"
cd Web
npm ci
npm run dev
```

另行启动 Cloud 的 8790 端口，打开 `http://127.0.0.1:5173`。输入团队访问令牌后进入助手；本地未启用鉴权时可留空。没有官方 SDK 时仍可使用对话、任务、记忆与设置。官方参数在“接入设备”内填写；未完成官方鉴权时不能导入新 SN。已有设备须先完成官方配网与绑定。

```bash
npm test
npm run build
```

兼容性回归需安装 FFmpeg，并执行 `npx playwright install chromium firefox webkit`、`npm run test:browser`。Windows 若需同时验证本机 Chrome/Edge，先设置 `$env:EG_BRANDED_BROWSERS='1'`。测试使用 SDK/API 替身和合成视频，不代表硬件取流通过；恢复官方 Demo 后额外测试真实表单加载与返回。本轮结果见 [Web 0.2 验收](../Docs/WEB-PRODUCT-PARITY.md)，此前接入与 iOS 合并检查见 [兼容性复审](../Docs/WEB-IOS-COMPATIBILITY-REVIEW.md)。

构建后将 Cloud 的 `EG_WEB_ROOT` 设置为本目录 `dist` 的绝对路径，即可同源托管。恢复的 SDK 不进入 Git，CI 因而只检查自有代码，不能验证真实媒体连接。官方握手、iOS 联调、模型配置、数据边界和硬件验收见 [接入指南](../Docs/LIVE-DEVICE-INTEGRATION.md)。

## 官方 SDK 工作区

页面顶部“切换至官方 SDK”可在五栏应用和原版 Demo 之间切换。首次使用需额外恢复完整 Web Demo：

```bash
# 在仓库根目录
python3 scripts/import_official_web_demo.py "/资料包/demo工程/WebSDKDemo"
cd Web
npm ci
npm run build:official
npm run dev
```

仍需按上文恢复 `/sdk/index.js`。官方原始 UI 与 UMD 不入 Git，缺失时工作区会显示恢复步骤。`build:official` 之后再 `npm run build` 才会把官方界面加入可部署 dist。可按 T8171 / T8214 导出手动硬件检查记录；返回前导出，刷新不保留记录。

原版 AI 面板点击开始会采集 10 帧并自动提交官方模型；在 Cloud 配置 `EG_OFFICIAL_AI_KEY`，不要放入 Web 环境。两端差异与完整操作见 [工作区指南](../Docs/OFFICIAL-SDK-WORKSPACES.md)。

## 数据与平台范围

- 设备、Skill、录像和证据属于当前团队空间；个人对话、记忆、提醒偏好使用浏览器安装标识，不会自动与另一台 iPhone 的个人记录合并。这里没有新增云账号或多租户授权。
- 安装标识、聊天草稿和待重试请求保存在 `localStorage`；存储受限时仍可使用当前页面，但不承诺刷新恢复。团队令牌及官方凭证只保留在内存。退出清除本机草稿；刷新后需重新输入令牌。
- Web 提供应用内提醒；iOS APNs 不会变成浏览器推送。网页关闭后无系统推送，语音输入可使用系统键盘听写。
- 直播及 Agent 新图采集保留现有会话协议。离开到任务 / 记忆 / 设置、切换设备或官方工作区、退出或页面进入后台时停止当前取样。助手和摄像头页间可以保留同一直播。
- 真机持续 Skill 发布仍受服务端能力检查限制。保存草案、完成设备准备或通过离线回放，都不意味着真实摄像头任务已运行；页面显示当前阻塞原因。
- 录像通过携带团队鉴权的请求读取，播放器使用临时 Blob URL；当前可能需要下载完整文件，移动端建议使用短片段。文件上限 150 MB，未填写拍摄日期时保留未知，不能用上传日期替代。

## demo 云端兼容更新（2026-10-16）

demo 产品入口为 https://demo.47.131.21.137.sslip.io/ ，沿用该环境的团队令牌。产品五栏与官方 SDK 切换同源托管。

10 月 16 日 13:35（新加坡时间）最终发布为 `tools-3c13da608c1867d8/web`，入口资源 `index-DCwGSe6f.js`。服务端继续使用已部署的 Codex/早晚报告版本，iOS 与 Web 请求契约均完成真实只读工具联调。后续诊断采集更新独立进行，不能将提示词记录数量视为 Codex 模型调用次数。

新增可选自动记忆设置和来源原话，旧后端无 `automaticMemory` 时不显示；`metadata_only` 事件明确标为仅设备报告。服务器已支持早晚两份报告，本版 Web 仍展示原每日概况控件，因此保存时显式只发送旧字段，不能回传未显示的 `morningReport/eveningReport/morningHour/eveningHour`。关闭概况按服务端兼容规则关闭订阅；本轮没有替换为另一个分支的新版设置 UI。

完整后端/部署差异与测试见 [demo 联调记录](../Docs/DEMO-TOOLCHAIN-DEPLOYMENT.md)。浏览器测试中的设备与回执替身不是物理设备验证。
