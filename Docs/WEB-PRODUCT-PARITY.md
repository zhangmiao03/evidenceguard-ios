# Web 0.2：新版 iOS 功能对齐与验收

开发分支：`dongrunze`。基于已同步 `main@0959463` 的代码，实现五个产品区并保留现有官方设备链路。本文描述代码与测试范围，线上部署和硬件验收另行进行。

## 实现与接口

| 页面 / 流程 | 源码 | Cloud 接口 |
| --- | --- | --- |
| 五栏导航、团队连接、设备选择、SDK 切换 | `Web/src/App.tsx` | `/api/bootstrap`、`/api/devices`、`/api/captures` |
| 主会话、话题、回复与取消 | `Assistant.tsx` | `/api/agent/conversations/main`、`/api/agent/conversations`、`/api/agent/runs`、`/api/runs/{id}/cancel` |
| 只读历史范围与录像定位 | `Assistant.tsx` | Agent `executionMode=history` + `historyFilter`；历史使用独立的 `-history` 会话流 |
| 主动提醒、依据与反馈 | `Assistant.tsx`、`Personal.tsx` | `/api/personal/messages/{id}/feedback`、`/api/personal/inbox/{id}/read` |
| Skill 草案与圈选 | `Skills.tsx` | `/api/skills/drafts`、`PATCH /api/skills/{id}`；携带 `revision`，不覆盖其他客户端新版本 |
| 能力检查、试跑、验收、确认 | `Skills.tsx` | `capability`、`trials`、`deployment`、`confirm`；人工预期、报告版本、人工核验和来源确认分别保留 |
| 任务状态和设备占用 | `Skills.tsx` | `lifecycle`、`recheck`、`replay-acknowledge`；409 的占用列表须人工确认，提交精确 `executionEpoch` |
| 记忆和提醒设置 | `Personal.tsx` | `/api/personal/memories`、`/api/personal/preferences`；显式保存，失败保留编辑并可重试 |
| 录像上传、索引、回看 | `Skills.tsx`、`ProductUI.tsx` | `/api/recordings`、`/api/recordings/{id}/index` 及受保护媒体路由 |
| 直播、帧挑战、新图回传 | 原有 `LiveView.tsx` | `/api/media-sessions` 及 heartbeat / commands / frames / stop |
| 原版 Demo | 原有 `OfficialWorkspace.tsx` | 原始 SDK 与代理协议，返回前执行停止握手 |

### 后端新增能力

`POST /api/agent/conversations/main` 不需要用户提供会话 ID，必须通过团队鉴权和有效安装标识。事务内检查已有绑定；已有 iOS 主会话保持原 ID；新客户端生成稳定主会话。重复请求、刷新和多标签不会产生多个主收件箱，也不会把独立话题重新绑定为主会话。没有改变原来 iOS 的绑定接口。

所有 Skill 激活门禁仍在后端。浏览器不会因按钮点击自行把任务标记为运行，也不会用测试图冒充官方现场。

### 提示词与接口说明同步

2026-10-14：修复了助手仍将 Web 描述成仅设备/直播工作台的问题。普通对话与主动评估共用 `harness/runtime.py` 的 `PRODUCT_GUIDANCE`；两端任务详情实际入口为“继续设置守护”，并使用“对象 / 条件 / 确认”编辑。服务端生成的草案摘要也提供两端入口，不能只修模型提示词而继续返回旧操作说明。

- iOS“我的 → 通知与提醒”自动保存偏好；Web“设置 → 通知与提醒”需点击“保存提醒设置”。iOS APNs 与 Web 应用内提醒分别说明；聊天没有记忆写入或设置修改工具。
- 对话请求没有客户端平台字段；媒体会话 `platform` 只代表采集端，不能据此认定提问者使用 iOS 或 Web。设备 ID 和名称使用能力/任务回执，不能固定套用 `cam-a/cam-b`。
- 图片核验提示词兼容事件、直播取样和合成来源；来源记录时间不保证是设备拍摄时间。`visual-review-v2` 隔离旧提示词缓存，原有调用额度不重置。主动看图工具返回文字核验回执，并不把原图直接返回给主模型。
- `/api/bootstrap.integration` 区分前台链路已实现与真机未验收；`/api/skills/{id}/publish` 仍始终阻止真机发布。OpenAPI 补充草案、设备登记、帧时间和预留规则字段说明；GET/HEAD 与 GET/POST 各有独立 operationId。HTTP 路径、请求字段和确认流程保持兼容。
- 模型实际选择来自服务端配置；没有新增提示词管理、图片生成或客户端任意换模型接口。`observe_frame` 仍是包裹区域执行器，宠物/车辆需求不因此获得执行能力。

`test_prompt_contracts.py` 检查实际发给 Provider 的消息、两端草案回复、只读工具范围和缓存升级；`test_web_product.py` 检查真实 HTTP 编辑/发布限制及 OpenAPI。这些是协议回归，不代表外部模型回答质量或硬件验收。

本次本地回归：Cloud **189 项通过**，Web 协议 **4 项通过**，TypeScript 与生产构建通过。下文 `fc0243b` 的浏览器/iOS CI 记录属于此前功能提交，本次 CI 以 PR 当前提交检查为准。

## 交互与状态约定

1. 助手支持不选择摄像头的普通任务对话；要观察新画面，选择设备并保持可用的前台直播。历史查询只访问已存资料。
2. 一次消息具有持久请求 ID。请求失败保留原文，重试复用 ID；服务端已接收的请求可从会话恢复。切换设备 / 停止直播时，迟到的现场请求也会被取消。从独立话题进入新任务时，迟到的回复只属于原话题，不会清空主对话草稿或混入主消息流。
3. 主对话承接主动提醒，独立话题不改变该绑定。现场与历史聊天分别保存草稿和消息流，避免把历史证据混作当前状态。
4. Skill 编辑采用“对象 → 条件 → 确认”。支持两台设备分别圈选区域，目标属于主观察视角。坐标使用画面 0–1 比例，可鼠标 / 触摸拖动，也可键盘输入。
5. 保存草案不会启用。回放启用要求服务端能力通过、报告未过期且对应当前版本、人工核验、回放来源确认。真机执行器未就绪时保留草案和阻塞原因。
6. 停止任务、移除记忆和抢占摄像头均有具体确认。复核只请求新证据，不直接把未知改成正常。
7. 提醒设置使用显式保存。后台刷新不会覆盖未保存编辑；服务错误保留编辑。每日概况使用配置时区，历史查询的“今天 / 昨天”沿用后端上海时区并在界面标注。
8. 桌面侧栏和手机底栏共用五个入口。弹窗使用原生 `dialog`，支持焦点约束、Escape 与关闭后焦点恢复；减少动效偏好沿用原样式。

## 与原生平台的差异

| 项目 | Web 0.2 |
| --- | --- |
| 系统推送 | 当前为应用内提醒；未实现 Web Push / Service Worker，不使用 iOS APNs 令牌 |
| 语音 | 可使用系统键盘听写；不宣称具有 Apple 本地语音识别或持续双向语音机器人能力 |
| 个人记录同步 | 同一浏览器安装标识可恢复；不同 iPhone / 浏览器的个人记录不会自动合并；摄像头任务仍在团队内共享 |
| 本地保存 | 聊天草稿、请求 ID、安装标识在 localStorage；存储禁用时降级为当页状态 |
| 官方 SDK | 可恢复并切换原版 Web Demo；不会把官方 Web 尚未提供的配网功能伪装成可用 |
| 录像回看 | 鉴权下载为临时 Blob URL，关闭组件后释放；大录像可能占用较多内存，当前建议短片段 |
| 真机持续守护 | 本次不绕过后端未就绪的发布门禁；需真实设备与对应执行器验收 |

## 启动与团队联调

1. 拉取 `dongrunze`，同时更新 Cloud 和 `Web/`。旧 Cloud 缺少主会话初始化接口，会显示恢复失败；不要只替换前端构建目录。
2. 按根 README 启动本机 Cloud 8790，配置真实模型密钥；本次测试使用替身模型和合成素材，不需要生产密钥。
3. `cd Web && npm ci && npm run dev`，访问 `http://127.0.0.1:5173`；使用本机 HTTPS 或可信 HTTPS 服务进行手机联调。带凭证的普通局域网 HTTP 会被拒绝。
4. 无硬件时先验收五栏、聊天、记忆、任务草案和回放流程。SDK 恢复方法见 Web README，恢复的主办方文件不入 Git。
5. 真机测试：官方绑定 → 本产品登记 → 直播 → 请求新图 → Agent 观察 → 切换官方工作区 → 返回重新鉴权；核验停止回执、图像来源、时间和错误状态。

生产构建使用 `npm run build`；Cloud 设置 `EG_WEB_ROOT` 为 `Web/dist` 绝对路径后同源提供页面与 API。更新 GitHub 分支不会自动证明线上服务已部署。本次不更改线上环境或 TestFlight。

## 自动化验收

命令：

```powershell
# 仓库根目录，已安装后端依赖
.\.venv\Scripts\python.exe -m pytest -q
python scripts/check_repository.py
cd Web
npm test
npm run build
npm run test:browser
# Windows 已安装 Chrome/Edge 时可额外验证
$env:EG_BRANDED_BROWSERS='1'
npm run test:browser
```

新增浏览器用例覆盖五栏与无横向溢出、临时记忆及删除确认、提醒设置失败重试、无设备对话与请求去重、历史范围、会话/草稿恢复、主动消息反馈、圈选保存、版本冲突、设备占用人工确认、回放验收门禁、录像上传及播放错误。继续运行原有直播、逐帧回退、SDK 切换和存储受限回归。

后端增加真实 HTTP 合同测试：主会话初始化鉴权、幂等、重启恢复、保留原生绑定；普通助手无需设备；消息去重；偏好/记忆隔离；共享设备草案；旧版本编辑拒绝；官方设备未验收时禁止启用。

2026-10-14 本机结果：Cloud **182 项通过**；Web 协议 **4 项通过**；TypeScript 与 Vite 生产构建通过；Playwright **152 项通过、4 项跳过**。浏览器覆盖 Chromium、Firefox、Windows WebKit、iPhone 尺寸 WebKit、已安装的 Chrome 与 Edge。跳过的是 Windows WebKit 缺少 `requestVideoFrameCallback` 的两种降级取帧场景（桌面和手机尺寸各两项），不计作通过；不支持取帧时明确报错的检查仍执行。

录像上传用例通过临时本机 HTTP 接收端验证实际收到的文件字节，避免把 WebKit 测试拦截器未暴露 File 请求体误判为上传失败。桌面与手机页面截图已检查，五栏没有横向溢出。

浏览器自动化使用 API/SDK 替身；官方原版 Demo 本机加载检查不代表真实账号或设备连接通过。测试没有调用生产模型、发布真实守护、部署线上服务或上传 TestFlight。

### GitHub CI 最终结果

受测功能提交：`fc0243bdb8886eedc80615945c286bdb9f9f1b42`。[Checks 四项全部成功](https://github.com/zhangmiao03/evidenceguard-ios/actions/runs/38552925223)，完成于 2026-10-14 19:03（UTC+8）。后续提交仅补充文档结果并统一 Markdown 换行，不改变受测源码。

| 检查 | 结果 |
| --- | --- |
| Cloud / 仓库扫描 | **182 通过**；368 个受版本管理的文件检查通过 |
| Web 协议 / 构建 | **4 通过**；TypeScript 与 Vite 生产构建通过 |
| Linux Chromium / Firefox / WebKit / 手机尺寸 WebKit | **100 通过、4 跳过** |
| macOS 桌面 / 手机尺寸 WebKit | **50 通过、2 跳过** |
| 原生 iOS Simulator | 普通目标编译通过；**3 项 XCUITest 通过**；Swift 契约检查通过 |

CI 的 6 项跳过都是缺少主办方专有 Demo 文件；这些文件按仓库约定不上传。Windows 本机恢复 Demo 后，六种浏览器项目的原版表单加载与返回测试均已运行通过。普通 iOS Simulator 检查不包含官方 arm64 SDK 真机归档或 T8171 / T8214 硬件验收。
