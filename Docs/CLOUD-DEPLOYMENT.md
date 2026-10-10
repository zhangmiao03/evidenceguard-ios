# 单团队 iOS 测试环境

Ubuntu 24.04、Python 3.12、FFmpeg；单进程 Uvicorn 监听 127.0.0.1:8790，Nginx 对外提供 HTTPS。
不要增加 workers；摄像头命令锁目前在同一进程内。

## 鉴权

公网实例必须配置 `EG_REQUIRE_AUTH=1` 与至少 32 字符的随机 `EG_ACCESS_TOKEN`。
缺少令牌会拒绝启动。普通 API 使用 Bearer；手机在「我的 → 服务连接」填写 HTTPS 地址与团队访问令牌。
令牌按服务地址保存在手机 Keychain，不放入 App 包、UserDefaults 或版本库。

API 响应签发 6 小时的 Secure / HttpOnly 媒体 Cookie，让原生图片与 AVPlayer 能访问录像及 Range 请求。
该 Cookie 只允许媒体 GET / HEAD，不能访问对话、草案或修改接口；轮换团队令牌会同时失效旧 Cookie。
本版本是单团队共享数据空间，未实现多租户隔离或独立成员账号，尚不适合开放给公众注册。

模型 Key 仍留在服务端。配置文件 `/etc/evidenceguard/cloud.env` 为 root:evidenceguard / 0640；
数据在 `/var/lib/evidenceguard`；服务使用无登录权限的 evidenceguard 系统用户。
只有 `/api/health` 可匿名访问，不暴露模型或设备状态；其他接口和媒体均需鉴权。

## 安装

1. 安装 Ubuntu 的 `python3-venv`、`ffmpeg`、`nginx`。
2. 把 `Cloud/server/evidenceguard` 与 requirements.txt 打包为包含 `Cloud/` 的 tar.gz，不包含本机数据库、录像或凭证。
3. 通过已验证主机指纹的 SSH 上传到 `/tmp/evidenceguard-cloud.tar.gz`；环境文件上传到 `/tmp/evidenceguard-cloud.env`。
4. 上传并以 root 执行 `scripts/cloud_setup.sh 公网IPv4`。

脚本先启动后台服务，HTTP 仅开放健康检查及 ACME 验证路径，其余返回 426；HTTPS 配置完成前不能用于 App 真机连接。
上线检查：匿名 API 为 401；有效令牌能读 bootstrap；媒体 Cookie 的 Range 请求为 206；
令牌未通过 HTTP 发送；无摄像头时明确显示离线，不宣称 SDK 或实时守护已验收。

## HTTPS

有域名时绑定 A 记录后使用受信任证书。没有域名时，Certbot 5.4+ 可申请 Let's Encrypt 公网 IP 证书：
[官方说明](https://letsencrypt.org/2026/03/11/shorter-certs-certbot.html)。
IP 证书约 6 天有效，必须配置自动续期及 Nginx reload hook，并验证续期；签发前需要账号所有者同意订户协议。
普通自动分配 EC2 公网 IP 可能在停止后重新启动时变化；当前测试地址不等同于长期固定入口。

## 验证边界

服务器可用、模型配置就绪、模型实际调用、iOS 编译、iPhone 安装、视频播放、真实 SDK 摄像头验收需分别记录。
HTTPS 检查与 TestFlight 分发分别验收。2026-10-11 已创建 App Store Connect 应用记录并成功上传 `1.0 (1)`，后续 Beta App Review、iPhone 安装和真实摄像头验收仍待完成；详见 [TestFlight](TESTFLIGHT.md)。

2026-10-10：受信任 HTTPS 地址为 `https://34.218.51.85`；后台服务与真实文本模型调用已验证。HTTP 跳转 HTTPS；匿名数据 API 返回 401，带团队令牌返回 200。媒体 Cookie 的 Range/206、HEAD 与 JPEG 缩略图通过公网检查。媒体验证使用临时合成 H.264 视频，只验证传输，结束后已删除；没有将它用作识别或真实摄像头验收。证书自动续期每六小时检查，演练成功。
后端 100 项测试通过，iOS 模拟器及包含官方 SDK 的 generic iOS Debug 目标均编译通过（真机目标未签名）。
尚未完成 iPhone 安装与真实摄像头验收。
