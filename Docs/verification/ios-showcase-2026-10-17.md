# 新版 iOS 作品演示验收（2026-10-17）

## 本地结果

- TypeScript 检查和 Vite 生产构建通过。
- 合并远端 `d584dd3` 后重新构建并运行 Chromium、Firefox、WebKit、mobile WebKit：共 **32 项通过**。其中新版 iOS 演示 16 项，覆盖守护门槛、首尾图只读示例与缓存、暂停、同机冲突、修改后重新框选、历史检索、设备与记忆；流程内没有业务写请求。
- 其余浏览器回归覆盖图片/回复台账、连接恢复与筛选、视觉来源/向量详情，以及队友新增的私有 SeedLite 诊断元数据。旧图片分析用例已按当前页面先展开折叠区，保留正文和来源断言。
- Web 单元测试 **20 项通过**。
- Dashboard Python 测试 37 项通过。
- 内置浏览器已查看助手与守护页的实际排版；手机 WebKit 测试核对无横向溢出。

尚未以本轮变化重新编译原生 iOS 或测试硬件。网页为标记清楚的本地交互演示，真实摄像头控制仍由手机 SDK 执行。

## 发布记录

已于 2026-10-17 02:49 新加坡时间发布；前端源码提交 `80438af1a4091cc4a487484fe97c41e42d225a5b`，包含 `main@b321730` 和 `dongrunze@d584dd3`。

- 新前端路径：`/opt/evidenceguard-dashboard/releases/1f1f1bcbcbb3e301/web`。
- 原只读服务/采集器代码继续使用 `557230ac6105e6fb`；未部署本次合并的业务后端或新 SeedLite 服务，未上传 TestFlight。
- 只改变 `evidenceguard-dashboard.service` 的 `EG_DASHBOARD_WEB` 行。demo/team/review 及采集器的发布前后 PID 完全一致，采集配置摘要一致。只有 Dashboard HTTP 展示进程重启。
- 三个业务 `/api/health` 均为 200，未授权 `/api/bootstrap` 均为 401，原 App 鉴权保持。
- 本机服务验证 HTML、全部 12 个静态资源和网站 ZIP；公开 HTTPS 再次核对新 HTML、Dashboard JS/CSS、anker 头像及 ZIP 的 SHA-256，全部一致。
- 公开图片台账 170 条、最终回复台账 99 条，分页可读；三个环境快照均未过期。这是该时刻的记录数，后续可继续增长。
- 网站 ZIP 1,694,177 字节、15 个条目，SHA-256 `ec47b5844c6281c2be9bb0463941c373468f13293c37d440ef90be4833db270e`；内置浏览器已从解压后的独立静态 HTTP 根入口打开完整作品。

本轮专用回滚备份：`/var/backups/evidenceguard-dashboard/frontend-20261016T184920Z`。恢复该目录内的 `evidenceguard-dashboard.service` 到 `/etc/systemd/system/`，执行 `systemctl daemon-reload`、`systemctl restart evidenceguard-dashboard` 后核对即可。此目录使用 `frontend.json`，不应传给完整部署的 `activate.py --restore`。之前后端/采集器的回滚目录继续保留。

当前生效前端与采集器不是同一个 release：清理历史文件时，必须同时保留当前 `EG_DASHBOARD_WEB` 路径和服务的 Python/WorkingDirectory 引用，不能按最新目录排序删除。


内置浏览器已打开正式 HTTPS 地址，截图确认线上显示新版 anker 助手、蓝白界面、场景引导和脚本状态面板；截图留在本机 `Cloud/data/ios-showcase-live-20261017.png`。线上资产哈希与已通过四浏览器回归的本地构建一致。

只清理本轮 `/tmp/eg-dashboard-upload-1f1f1bcbcbb3e301` 的 192 个上传分片，回收 3,453,390 字节。当前新前端、旧观察器代码、业务数据和可用回滚备份均保留。
