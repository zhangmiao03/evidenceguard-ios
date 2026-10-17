# Dashboard 云端读取超时：排查、修复与线上验证

2026-10-17，验证入口：https://demo.47.131.21.137.sslip.io/dashboard?view=showcase

## 结论与复现

`Web/src/dashboard/cloud.mjs` 原来用 12 秒的 AbortController 定时器覆盖整个 JSON 下载，包括响应正文。触发时页面显示“云端读取超时，将自动重试”。这不是后端确认丢失数据，也不是模型调用超时。

线上 demo 快照含 3,172 条记录，约 1,681,485 字节。HTTPS 的三个 `/dashboard/` 代理块缺少 JSON 压缩；HTTP IP 入口虽配置了 gzip，但不会自动应用到独立的 HTTPS server 块。即使客户端发送压缩协商，实际响应仍是完整的未压缩 JSON。

| 检查 | 修复前 | 修复后 |
| --- | --- | --- |
| demo 数据传输体积 | 约 1.68 MB，无 Content-Encoding | 约 206 KB，Content-Encoding: gzip |
| 同一机器限速 100 KB/s、12 秒上限 | HTTP 200 已到达，但 12.01 秒时只下载约 1.28 MB，被中止 | 约 1.77 秒完整读取 |
| 服务器内部读取 demo 快照 | 约 0.68 秒 | 后端读取逻辑未修改 |
| 本机正常网络完整读取 demo | 曾观测约 2.61 秒，有网络波动风险 | 最终烟测约 0.67 秒 |

以上是本轮观测值，不是任意网络条件的耗时承诺。100 KB/s 为 curl 传输限速；诊断准确复现了“响应正常但正文尚未收完就超时”的条件，不能追溯用户此前每一次失败的具体网络速度。

当时三套业务服务均 active，无重启；内存使用约 1 GB / 4 GB，磁盘剩余约 21.6 GB，没有资源耗尽证据。当前采样循环约 14 秒，快照过期标志仍按原有 20 秒规则计算，未为消除提示而掩盖数据新鲜度。

## 代码与部署范围

- `Cloud/dashboard/eg_dashboard/nginx_routes.py`：在已有的 `/dashboard/` location 内启用 gzip，覆盖 JSON、JavaScript、CSS、JSONL，压缩等级 5、最小 1 KB、`Vary: Accept-Encoding`。不更改 App `/api` 路由或鉴权。
- `Web/src/dashboard/cloud.mjs`：完整读取时限改为 30 秒。请求仍可取消；真正卡住的正文仍会失败；成功后清理定时器。原轮询在请求结束后再等待 5 秒，保持不重叠请求、保留失败前快照和自动重试。
- 不删除、裁剪或伪造追踪记录，不更改模型、相机 SDK、摄像头取流或采集器代码。
- 新前端目录：`/opt/evidenceguard-dashboard/releases/c09e416d58bbe86d/web`。下载网站 ZIP 由相同前端文件重新生成，所有文件逐项核验。
- 仅重载 nginx、重启独立 Dashboard HTTP 展示服务。三套业务 PID 与采集器 PID 发布前后相同。

## 验证结果

- Node 全部 30 项测试通过，包含新增的 15 秒慢响应成功、已收到响应头但正文卡住时按时取消。
- nginx 路由 3 项测试通过：重复安装一致、保留其他配置、压缩仅作用于公开 Dashboard。
- TypeScript / Vite 生产构建通过。
- Chromium / mobile-WebKit 4 项浏览器回归通过：错误提示后自动重连、清理筛选、图片与向量记录及详情展示。此组使用受控本地测试数据。
- 部署后真实 HTTPS 验证：demo / team / review 快照均 200、gzip、`no-store`、采集连接正常；本次记录数分别 3,172 / 93 / 73，数量会随真实业务变化。
- 三套原 App `/api/health` 均 200，未授权 `/api/bootstrap` 均 401。Dashboard 写入尝试仍被 405 拒绝，未知环境仍 422。
- 线上 index 与所有 JS 逐文件 SHA-256 对照本地构建一致；网站 ZIP CRC 和其中全部 15 个前端文件核验通过。
- 没有调用模型、创建 Agent 任务或触发硬件。未进行 iOS 真机验收。

## 回滚

nginx 备份：`/var/backups/evidenceguard-dashboard/https-20261017T060310Z/nginx.json`。文件内保存此次修改前三个配置文件的内容；按记录路径恢复后，先 `nginx -t` 再 reload。

前端备份：`/var/backups/evidenceguard-dashboard/timeout-frontend-20261017T060920Z/`。实际改动的是 `/etc/systemd/system/evidenceguard-dashboard.service.d/99-sync-main.conf` 中的 `EG_DASHBOARD_WEB`，不是主 unit 文件中已被覆盖的旧值。恢复备份内的同名文件，执行 `systemctl daemon-reload` 和 `systemctl restart evidenceguard-dashboard`。旧前端 `/opt/evidenceguard-dashboard/releases/5d363250cc48ac86/web` 保留可回滚。

Python 服务路径、collector 路径、业务配置和数据库均保留；不要把本次前端 release 当作完整观察器 release 运行 activate.py。
