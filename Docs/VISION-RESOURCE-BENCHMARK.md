# 深度与光流：本机限额测试和模型

2026-10-14 完成第一轮 CPU 测试，用 WSL cgroup 分别限制为 2 核 / 4 GiB 和 1 核 / 2 GiB，禁用 Swap，仅使用 CPU。**这是本机 i9-14900HX 实测，不等于新加坡 EC2 的实测性能。**

- [完整实测报告：耗时、内存、组合回放与限制](../Cloud/vision-resource-lab/results/local-20261014/REPORT.md)
- [复现工具与 Agent 接入建议](../Cloud/vision-resource-lab/README.md)
- [三份 ONNX 模型：Git LFS 下载、校验与许可](../Cloud/vision-resource-lab/models/README.md)

初始候选为 DepthART 448 每秒一次 + DIS 光流每秒六次。在 1 核 / 2 GiB 配额的约一分钟单路文件回放中，完成 60 次深度、356 对光流；无因处理不及时跳过的输入时隙。切片循环处重置光流。尚未包含真实 SDK 取流、网络、多摄像头、云端 VLM 或同机其他服务的负载。

DIS 和 Farneback 是传统光流算法，不需要神经网络权重；光流至少需要同一相机按时间排序的两帧。普通单图深度在本实验中依赖模型，输出为相对深度，不能直接用于米制测距。云台运动会进入光流，需要保留相机运动状态。

原视频与抽帧输入不随仓库分发。报告保留逐帧 CSV/JSON 和处理效果预览；模型上传与实验脚本提交均不代表已接入或部署到生产后端。
