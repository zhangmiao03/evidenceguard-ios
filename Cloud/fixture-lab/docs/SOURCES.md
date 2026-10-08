# 来源与依赖记录

记录日期：2026-09-22。业务实现、界面、测试和合成素材在本任务中编写。

| 来源 | 用途 | 许可/使用情况 |
|---|---|---|
| [MediaMTX v1.21.1](https://github.com/bluenviron/mediamtx/releases/tag/v1.21.1) | 实际本地 RTSP 媒体服务器 | MIT；二进制下载到 .runtime，原许可证同目录保存；不随源码包分发 |
| [FFmpeg](https://ffmpeg.org/) | 原始图像编码推流和 RTSP 解码 | 使用本机现有 FFmpeg 8.1，构建启用了 GPL/libx264；源码包不包含该二进制 |
| [OpenCV](https://opencv.org/) | ArUco 检测/标记生成 | 使用 opencv-python-headless，包版本锁定；非云模型 |
| [FastAPI](https://fastapi.tiangolo.com/)、Uvicorn | HTTP 服务、生命周期启动/退出 | MIT / BSD 3-Clause，依赖版本见 requirements.lock |
| [React](https://react.dev/)、TypeScript、Vite | 响应式控制页面与构建 | MIT / Apache 2.0 / MIT，版本见 package-lock.json |
| [Lucide](https://lucide.dev/) | 界面图标 | ISC，版本见 package-lock.json |
| Pillow、NumPy | 程序化测试图像与像素处理 | 依赖元数据见 dependencies.json |
| MiiMiao 本地仓库 fe43a78 | 参考持久递增执行事件、独立于控制界面的任务调度边界 | 只阅读 run_event_repository.py、task_scheduler.py 与约束；本轮没有复制实现或改动该仓库 |
| 团队两份 PDF 及此前 v2/v3 计划 | 产品要求和待修正的状态设计 | 用户提供内部参考，未随源码包分发原 PDF |

合成场景由 Pillow 和 OpenCV 从几何图形生成，不含下载照片、人物素材或 Hugging Face 数据。两个视角是对应同一实验状态的示意图，不宣称物理真实多视角渲染。

Hugging Face 和社区 eufy SDK 只出现在先前调研，**本轮没有下载其数据、安装其 SDK 或登录 eufy 账号**。

摄像头实验室本身只负责可重复的双路画面和事件；MiiMiao 风格的 Tool Registry、durable run events 与自然语言 Skill 编译位于上层 `Cloud/server/evidenceguard/harness/`。当前 Provider 是可测试的确定性实现，接入正式模型时保持工具合同不变。

依赖元数据机器清单为 dependencies.json；源码锁文件保留确切解析版本。来源记录不替代正式发布前对整个依赖树的许可证审查。
