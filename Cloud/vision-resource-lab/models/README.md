# 测试模型：下载、校验与来源

这三份模型就是 [2026-10-14 实测报告](../results/local-20261014/REPORT.md) 使用的权重，原文件未修改，仅重命名为便于脚本使用的文件名。全部为相对深度模型；光流 DIS / Farneback 没有需要上传的神经网络权重。

| 本仓库文件 | 模型 / 输入 | 字节数 | 上游 |
|---|---|---:|---|
| [depthart224.onnx](depthart224.onnx) | DepthART MobileNetV4-M-slim-SPF，224×224 | 24,155,097 | [Fengxue93/DepthART](https://huggingface.co/Fengxue93/DepthART/tree/9e154201cd8fb3453c9def581997aaf1b4da3c22/onnx) |
| [depthart448.onnx](depthart448.onnx) | DepthART MobileNetV4-M-slim-SPF，448×448 | 24,155,097 | 同上 |
| [dav2small.onnx](dav2small.onnx) | Depth Anything V2 Small FP32，社区 ONNX | 99,060,839 | [onnx-community](https://huggingface.co/onnx-community/depth-anything-v2-small/tree/4472b7362082ad9968fee890ca0f1e5aca36b93d/onnx) |

合计 147,371,033 字节，约 147.4 MB / 140.5 MiB。完整源文件路径、固定 revision、原始下载地址、SHA256 均见 [manifest.json](manifest.json)。这是模型文件共享，尚未把模型装入线上服务或修改摄像头固件。

## 从我们的分支取回

需要 Git LFS，并使用有权读取本私有仓库的 GitHub 账号。在已有仓库根目录执行：

```bash
git switch dongrunze
git pull --ff-only origin dongrunze
git lfs install --local
git lfs pull origin --include="Cloud/vision-resource-lab/models/*.onnx"
python Cloud/vision-resource-lab/verify_models.py
```

新电脑也可以安装 Git LFS 后 `git clone --branch dongrunze https://github.com/zhangmiao03/evidenceguard-ios.git`。如果 `.onnx` 只有约 130 字节，说明取到的是 Git LFS 指针，尚未下载模型；执行上面的 `git lfs pull`。校验脚本会逐个检查实际体积与完整 SHA256。

也可在实验目录运行 `python prepare_models.py` 按清单从上游恢复；已存在且校验正确的模型无需访问上游。

## 署名与许可证

- **DepthART**：Feng Xue 等作者，官方项目 [xuefeng-cvr/DepthART](https://github.com/xuefeng-cvr/DepthART)。保存了 [作者 LICENSE](licenses/DepthART-LICENSE.txt)、[第三方声明](licenses/DepthART-THIRD-PARTY-NOTICES.md) 与 [该版本模型卡](licenses/DepthART-HF-MODEL-CARD.md)。原作者材料标为 CC BY 4.0；声明另列第三方及使用 Depth Anything V2-L 教师的限制，不能把整套权重一概解释为无限制商用授权。本仓库用于团队比赛研究，后续用途须遵守相应条款。
- **Depth Anything V2 Small**：来自 [Depth Anything V2](https://github.com/DepthAnything/Depth-Anything-V2) 项目，ONNX 转换来自 `onnx-community`。该转换版本的 [模型卡](licenses/DAV2-Small-ONNX-MODEL-CARD.md) 标注 Apache-2.0；随附 [Apache 2.0 完整文本](licenses/Depth-Anything-V2-APACHE-2.0.txt)。这份 Small 与上述 DepthART 教师 V2-L 是不同权重。
- 上述许可证和模型卡的取回地址固定在 [licenses/sources.json](licenses/sources.json)，不更改原作者许可。模型文件保持与上游 SHA256 一致。
