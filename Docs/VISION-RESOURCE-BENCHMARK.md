# 深度与光流：本机限额测试和模型

**默认查看黑白深度效果，近处亮、远处暗。** 三个模型的对照、单张 PNG 和原始测量数据已按实验批次整理。

![原图与三个模型的黑白深度对照](../Cloud/vision-resource-lab/results/local-20261014/depth-grayscale-comparison.jpg)

| 要查看的内容 | 入口 |
|---|---|
| 黑白效果、单张图片与本批文件说明 | [本批图册与文件导航](../Cloud/vision-resource-lab/results/local-20261014/README.md) |
| 完整性能报告 | [时延、内存、组合回放和验证边界](../Cloud/vision-resource-lab/results/local-20261014/REPORT.md) |
| 模型文件 | [Git LFS 下载、SHA256 与许可证](../Cloud/vision-resource-lab/models/README.md) |
| 复现代码 | [实验工具与运行方式](../Cloud/vision-resource-lab/README.md) |
| 实验批次 | [结果索引](../Cloud/vision-resource-lab/results/README.md) |

2026-10-14 完成第一轮 CPU 测试，用 WSL cgroup 分别限制为 2 核 / 4 GiB 和 1 核 / 2 GiB，禁用 Swap，仅使用 CPU。**这是本机 i9-14900HX 实测，不等于新加坡 EC2 的实测性能。**

初始候选为 DepthART 448 每秒一次 + DIS 光流每秒六次。在 1 核 / 2 GiB 配额的约一分钟单路文件回放中，完成 60 次深度、356 对光流；无因处理不及时跳过的输入时隙。切片循环处重置光流。尚未包含真实 SDK 取流、网络、多摄像头、云端 VLM 或同机其他服务的负载。

DIS 和 Farneback 是传统光流算法，不需要神经网络权重；光流至少需要同一相机按时间排序的两帧。普通单图深度在本实验中依赖模型，输出为相对深度，不能直接用于米制测距。云台运动会进入光流，需要保留相机运动状态。

原视频与抽帧输入不随仓库分发。报告保留逐帧 CSV/JSON 和处理效果预览；模型上传与实验脚本提交均不代表已接入或部署到生产后端。
