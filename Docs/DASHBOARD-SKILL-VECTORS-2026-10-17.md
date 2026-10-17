# 自定义 Skill 与向量检索展示

## 对应源码

- `Cloud/server/evidenceguard/visual_skills/harness.py`：以用户原话历史和当前规则交给配置模型，返回结构化 Interpretation。支持可见对象进入 / 离开固定区域；保留未修改条件，缺条件澄清，超能力说明原因。
- `schema.py`：title、target、selection（object / region）、trigger（enters / leaves）、confirmationSeconds（15–600）、completion（once / continuous）。不是任意生成代码并执行。
- `service.py`：保存草稿版本，异步结果核对版本；取帧、选框、用户确认分开。激活需要有效的新 iOS 直播帧，历史原片不能代替实时画面。
- `video/index_v2.py` 与 `video/search.py`：视频和关键帧各自余弦排名，经 RRF 融合与窗口合并；有限视频复核后匹配优先，保留候选和不确定状态。模型估计的时间点仍需播放原片核对。

## 实际验证材料

通过服务器当前部署的真实 API，用独立安装身份创建一份公开比赛草稿，再继续修改同一草稿。真实执行器 `codex-app-server-v1`，模型 `doubao-seed-2-1-lite-260915`。

| 条件 | 首次生成 | 继续修改 |
| --- | --- | --- |
| 原话 | 帮我看着桌面上这个红盖水瓶，离开框选区域后观察30秒，只提醒一次。 | 改成观察45秒，持续提醒，其他条件保持不变。 |
| 对象 | 桌面上的红盖水瓶 | 保留 |
| 框选 / 条件 | object / leaves | 保留 |
| 观察跨度 | 30 秒 | 45 秒 |
| 提醒方式 | once | continuous |

两个返回均为 draft / select，`canActivate=false`。没有调用 frame、selection、activate，也没有打开直播或修改硬件。文字编译没有图像输入；页面配图来自此前公开的 T8171 实拍录像第 44 秒，用于解释下一步框选。浏览器绘制的框不发送至后端。

生成材料独立保存于 `briefing/demo/skills.json`。采集器只投影该显式公开材料的白名单字段，不扫描其他私有 visual_scenes。当前公开原片的 ID 与 SHA-256 必须同时匹配；源片删除或替换后案例撤下。参考帧须验证媒体哈希；密钥、安装身份、路径、任意附加字段不发布。维护脚本默认复用同编译器源码、同来源的结果，避免重复生成付费草稿。

向量页使用已保存的两次真实查询：“找出有人拿起桌面水瓶的片段”与“查找与参考图中水瓶外观相似的目标”。两次各有 3 个召回候选、2 个尝试复核，2 个返回窗口匹配；并非检索准确率或全时段覆盖率。第三个未复核候选保持独立状态。参考图是实际规范化查询原件。窗口封面和帧带来自精确关联的索引帧，不宣称封面就是估计事件发生瞬间。

## 页面与测试

“自定义 Skill”进入主导航；保留 `/dashboard?view=tasks`，旧版 Skill 和任务放入折叠详情。30 秒导览增加真实 Skill / 检索入口，三个交互场景仍明确为脚本示例。

新测试覆盖版本差异、条件保留、无硬件写请求、候选复核状态、图文查询切换、事件及索引帧定位、移动端溢出；数据层覆盖录像 / 窗口 / 索引签名隔离、过期索引不配图、白名单与撤回。测试媒体为测试夹具，和公开真实案例分开。浏览器验证不替代 iOS 真机与硬件验收。

部署仅切换独立 Dashboard 的前端、HTTP 模块和只读采集器，保留业务服务与当前环境映射；先备份并核对现有配置，验证失败回滚本次改动。

## 已完成的验证与发布

2026-10-17 09:21（新加坡时间）发布代码 `342ca85`，核心实现 `c74fdd5`。线上 release 为 `/opt/evidenceguard-dashboard/releases/ebbf1d57639d3da6`。备份位于 `/var/backups/evidenceguard-dashboard/skill-vectors-20261017T012112Z`。

- TypeScript 与生产构建通过；42 项 Dashboard 后端测试在本地和服务器均通过。图片关联单元检查通过。
- Chromium、Firefox、WebKit、移动 WebKit 的 20 个导览 / Skill / 检索用例全部通过；另有 2 个 Chromium 原有评委阅读回归通过。Firefox 首次失败来自测试 PNG 不合法，换为可解码夹具后复测通过。移动端额外修复折叠导航被横向布局拉高，并验证导航高度。
- 公网免登录实测：两版真实规则、两次真实查询、六张候选预览与十二张索引帧可见；正文与图片从真实公开记录读取。首次生成与继续修改、候选切换、事件 / 帧定位和图文查询切换通过，浏览器未发出业务写请求。
- 桌面 Chromium 与已安装 Chrome 实际播放 65 秒 H.264 原片并定位命中时间。移动 WebKit 验证页面、图片与定位状态；没有宣称 Windows WebKit 的视频解码或 iOS 真机验收通过。
- 公网首页、14 个静态资产、整站 ZIP 与本地构建逐一 SHA-256 匹配；Skill 配图也与记录的内容哈希匹配。ZIP SHA-256：`a01411ffdbdbf891a3ccf962590044eff1d57f063232b77c9a6e8622e3de4e39`。
- demo / team / review 快照均非过期。三个原业务进程 PID 发布前后完全一致，健康检查正常，原 `/api` 鉴权保持；新采集器成功投影公开 Skill 案例。
- 清理本次两个传输暂存目录及未启用的中间 release，释放 10,481,405 字节；当前完整 release、上一个前端与采集器版本及回滚备份保留。发布采用内容哈希验证的增量传输，最终 53 个文件（包含整站 ZIP）与完整本地发布包一致，不依赖已删除的中间 release。

入口：[自定义 Skill](https://demo.47.131.21.137.sslip.io/dashboard?view=tasks&environment=demo) · [视频检索效果](https://demo.47.131.21.137.sslip.io/dashboard?view=vectors&environment=demo)。本次操作与截图留在未纳入 Git 的 `Cloud/data/audit-20261017-skill-vectors/`，不在仓库提交用户运行数据。
