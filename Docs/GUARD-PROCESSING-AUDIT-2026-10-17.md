# 守护逐次诊断补齐

## 原缺口与修改

原有 SceneHarness 已经执行 DepthART / DIS，并把可用的辅助图交给 VLM，但后台守护任务没有建立 Recorder 上下文，处理诊断和最终采纳结果未形成同一条可查询记录。公开图片副本最多采集六项，守护的四张 RGB、两张深度与一张光流共七项时还会漏掉最后一张。

本次在每个实际调度的守护检查上建立独立 trace；空轮询不产生任务记录。记录取图、预处理开始与结束、跳过/失败原因、模型输入与返回、约束后的判断、最终提交/丢弃/取消。相同时间戳下用逐次序号保证阶段顺序。新增 lastGuardRunId / evidence.guardRunId 为附加字段；现有状态机、提示词正文、预算、取图频率、帧来源检查和硬件接口不变。

逐次记录仍写入独立 observability SQLite 的有界队列，重要记录按整条 trace 留存，超过容量按旧任务淘汰。输入副本上限改为八项，图像角色来自同一次请求的相邻说明，不按时间或人物外观猜测关联。图像缓存继续有大小限制；过期、缺图、采集失败不假装成功。逐次事件本身不存二进制；实际模型调用的图片由已授权的 opt-in observer 保存。模型尚未调用便中断时，诊断仍可保留，未提交图片不会被称为模型输入。

捕获开关仍有效；私有 PRIVATE_CONTENT 上下文优先于公开调试采集。密钥沿用运行时和导出时双重脱敏，不进入提示词正文、截图或仓库。没有更改免登录 Dashboard 的只读边界和业务 API 认证。

## 页面与兼容性

图片理解顶部增加“这次守护，如何得出结果”，四步展示具体状态、耗时与最终采用结果；展开即可查看提示词、模型正文、每步诊断与完整输入图片。最近十二次检查中的实时守护与保存视频验证分别标识、分别计数。原有公开录像深度/光流复算仍保留，并明确其离线性质。

部署能力从当前业务进程的启动状态读取，脱离公开案例文件；旧环境没有 guardTracking 时不会被显示成已支持。配置就绪不等于已执行、已通过或已取得真机验证。

## 无设备时的可执行验证

Cloud/dashboard/verify_guard_replay.py 只读取已经公开的原片，校验指定录像 SHA256 与公开媒体清单，提取真实帧，用已部署 SceneHarness、真实 DepthART 与当前配置的真实 VLM 处理。业务数据使用自动清理的隔离临时库；不调用取流、控制、通知或运行中的场景管理接口。

脚本仅将标有 stored_video_replay 的运行记录写入现有独立追踪库，并核验六张模型输入副本的哈希、提示词/模型/最终记录数量、落库错误及密钥脱敏。回放元数据不会改为 official_live_*，生产 pair_gate 应返回 LIVE_SAMPLE_REQUIRED。公开录像的 DIS 离线复算与实时光流门槛是两个检查，不能用前者声称后者通过。

部署后以当前 demo release 的 venv 执行：

```sh
<demo-release>/venv/bin/python <dashboard-release>/verify_guard_replay.py \
  --recording video-c375d572c0cc44bd \
  --sha256 aca9ab9b0058cd1d45522e8cbf03b58a16ef330df2a052bd33f0807a54dec2c0 \
  --first 44 --second 44.5
```

命令须在现有授权服务器维护通道运行，凭据只在内存中读取。脚本没有开放新的公网执行接口。

## 已执行检查与待验证范围

本地后端：482 通过、13 项环境相关跳过；Dashboard Python：41 通过；浏览器：16 通过，覆盖 Chromium、Firefox、WebKit、手机 WebKit。新增检查包含取消、取图失败、非法来源、任务版本变化丢弃、不可用预处理、预算跳过、遥测故障、私有内容边界、第七张光流图和正文可查看。没有把这些替身测试当作真实设备数据。

部署后真实保存录像验证已经通过：使用原片 44 / 44.5 秒，DepthART 完成（总预处理 1205.33 ms），生产光流门槛返回 LIVE_SAMPLE_REQUIRED；豆包模型 doubao-seed-2-1-lite-260915 返回（3794.82 ms）。八条实际链路记录、一组提示词和模型响应、六张输入副本已落库；副本经服务器及公网二次 SHA256 核验。最终判断为目标在区域内，依据是参考和当前图背景对齐、区域内可见红盖透明水瓶。这是模型的可见性判断，不是人工标注的准确率评估。

公网实际页面另以 Chromium 和手机 WebKit 核验：可选择该回放、打开真实 RGB 与深度图、查看完整提示词和返回正文，页面无脚本错误或横向溢出。后台真实守护调度产生的不可用记录也会展示；记录存在不代表设备已验收。

后端发布为 tools-1ba936f71aaa3edf，源码 d09a111；Linux 494 通过、1 跳过。跳过项依赖仓库内模型权重路径，服务器独立安装权重已校验，以上真实 DepthART 调用另外通过。迁移预检使用业务库副本，保留计数不变；team / review 原进程未重启，私有配置文件哈希不变。

新提醒证据通过显式 guardRunId 和最终提交回执（evidenceId、alertPublished、committed）关联本次模型调用；不使用相近时间或人物外观匹配。缺失、丢弃和私有记录不会被错误关联。发布前合并队友 a891276 / 82c4e79 的助手与独立报告改动。Web 单元检查 27 项通过，Dashboard Python 42 项通过。

扩展浏览器检查覆盖产品页面与工作区：127 通过、8 项预置条件跳过、1 项失败。失败是测试 PNG 的 IDAT 校验码损坏，已用有效 PNG 替换，并增加实际解码尺寸断言；对应四浏览器检查重新通过。原生官方 bundle 缺失和 WebKit 不支持的帧 API 分支没有被计为通过。实时守护与保存视频验证分别保留最近十二次，繁忙实时检查不会挤走仍在快照中的回放项。

用户当前没有设备在手，实时 iOS SDK 取流、新鲜帧、≤1 秒相邻帧与硬件动作不属于本轮已验收范围。

## 最终发布与复核（2026-10-17 08:30，UTC+8）

入口：[图片理解与守护诊断](https://demo.47.131.21.137.sslip.io/dashboard?view=images&environment=demo)。选择“保存视频验证”，可查看本次实际运行的四个阶段；展开“提示词、模型正文与每步诊断”查看正文和全部六张输入。实时检查与回放分开选择，设备未提供有效画面时如实显示无法确认。

| 项目 | 已核实状态 |
| --- | --- |
| Dashboard 前端与采集器 | 源码 `40fda3cc8e4090cf7fce63c2b734ddd50ccd66fb`，目录 `/opt/evidenceguard-dashboard/releases/32f923f59f972c5c` |
| 实际生效的服务配置 | `evidenceguard-dashboard.service.d/99-sync-main.conf` 与 `evidenceguard-dashboard-collector.service.d/99-sync-main.conf`，位于 `/etc/systemd/system/` |
| 后端守护实现 | `d09a111`，目录 `/opt/evidenceguard-demo/releases/tools-1ba936f71aaa3edf`；进程已加载模块、磁盘与参考源码指纹一致 |
| 静态网站下载包 | SHA256 `948feef2827c219db93cfa59525b1f2d536ad4d8d331d87e8da8cdb18d97372c`；公网下载与发布文件一致 |
| 本次切换影响 | 仅重启 Dashboard 与采集器，三个业务服务 PID 和环境映射保持；健康检查通过，业务 API 仍需认证 |
| 媒体与检索 | 12 张真实入库关键帧、2 个公开检索案例、5 张原有离线处理图片仍可读 |
| 真实模型链路 | 8 条记录、6 张输入副本，公网逐一核对字节摘要；模型返回与保存结果一致 |
| 线上界面 | Chromium 与手机 WebKit 均通过；RGB 与深度图解码宽度 640，提示词、真实模型正文可打开，无页面异常或横向溢出 |
| 服务端采集器检查 | 最终发布目录运行 42 项检查全部通过；demo / team / review 快照均非过期状态 |

发布包含队友同步的助手和独立报告改动。使用实际生效的 systemd drop-in 切换；先核对前一配置摘要，变更发生冲突时停止并回退本次改动，未覆盖队友的新配置。

本次切换前的 Dashboard 配置备份在 `/var/backups/evidenceguard-dashboard/frontend-and-collector-20261017T003000Z`。目录内 `manifest.json` 记录实际 unit 路径与前后发布目录，两个备份分别为 `evidenceguard-dashboard.service.d-99-sync-main.conf`、`evidenceguard-dashboard-collector.service.d-99-sync-main.conf`；原采集器配置保存在 `collector-config.json`。需要回退时，先确认当前仍是本次发布，再恢复这两份 override 及采集器配置中的 `reference` / `revision` 字段，执行 `systemctl daemon-reload` 并重启这两个 Dashboard 服务，随后核对 HTML、快照与业务健康。若配置已被后续部署修改，先对比差异，不直接覆盖整份配置。后端是独立发布，Dashboard 回退不要求回退业务服务。

清理了四个本次上传临时目录、一个重复的后端上传副本和一个从未启用的 Dashboard 中间版本，共 16,748,679 字节。删除前逐项核对绝对路径和当前服务引用；运行目录、上一可回退版本、业务图片、录像和数据库保留。清理后可用空间约 22.4 GB。

本地验收原始输出、实际页面截图和哈希检查存放于忽略目录 `Cloud/data/audit-20261017-guard-processing/`，不把真实媒体或运行快照提交仓库。回放 trace 为 `guard-e379b8ecabdf473588b071a9cd2fbb70`，仅用于维护核对；网页默认使用可读标题。
