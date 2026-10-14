"""Build a readable report from actual results, without invented benchmark values."""
from pathlib import Path
import argparse
import json

ROOT = Path(__file__).resolve().parent
NAMES = {
    'depthart224-224': 'DepthART MNv4-M-slim-SPF 224',
    'depthart448-448': 'DepthART MNv4-M-slim-SPF 448',
    'dav2small-518': 'Depth Anything V2 Small（社区 ONNX）',
    'dis': 'DIS FAST 光流', 'farneback': 'Farneback 光流',
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run')
    args = parser.parse_args()
    folder = ROOT / 'results' / args.run
    lines = [
        '# 本机 CPU 限额测试结果', '',
        f'批次：`{args.run}`。详细环境、模型版本、SHA256、资源限额及逐帧计时均保存在本目录。', '',
        '**这是本机 i9-14900HX + WSL 的实测，不是 EC2 实测，也不是云服务器性能等价仿真。**', '',
        '资源档位：整机预算 2 CPU / 4 GiB；视觉工作进程预算 1 CPU / 2 GiB。均禁用交换内存、只用 CPU，并由每个进程读取 cgroup 验证限额。', '',
        '## 1. 单项测试', '',
        '时延包含 JPEG 读取/解码、预处理、计算和简单输出统计；不包含模型加载、预热、网络、视频解码、图片保存、VLM 和排队。深度每项 19 张、预热 2 次；光流每项 113 对，帧间隔约 167 ms。P95 仅描述本批小样本，不代表服务 SLA。', '',
        '| CPU / 内存 | 方法 | 实际输入宽×高 | P50 | P95 | 进程峰值 RSS |',
        '|---|---|---:|---:|---:|---:|',
    ]
    results = []
    for profile, label in [('server-budget', '2 / 4 GiB'), ('worker-budget', '1 / 2 GiB')]:
        for name, human in NAMES.items():
            file = folder / profile / name / 'result.json'
            if not file.exists():
                lines.append(f'| {label} | {human} | — | 未完成 | 未完成 | — |')
                continue
            result = json.loads(file.read_text())
            results.append(result)
            if result['kind'] == 'depth':
                height, width = result['model_input']['actual_nchw'][-2:]
            else:
                height, width = result['flow_shape'][:2]
            timings = result['timings_ms']['pipeline_ms']
            lines.append(f'| {label} | {human} | {width}×{height} | {timings["p50"]:.1f} ms | {timings["p95"]:.1f} ms | {result["peak_process_rss_mib"]:.1f} MiB |')
    lines.extend(['', 'RSS 包含 Python、运行库和模型等进程内存；cgroup 的整个进程组内存峰值与 OOM 计数另外保存在 JSON。两档测试的线程数、CPU 调度和测量时段不同，不能把个别单线程更快的结果理解为“CPU 越少越快”。', '',
        '## 2. 一分钟组合回放', ''])
    paced_file = folder / 'sustained-1cpu-2g' / 'result.json'
    if paced_file.exists():
        paced = json.loads(paced_file.read_text())
        lines.extend([
            '配置：1 CPU / 2 GiB；单路输入，DepthART 448 每秒 1 次，DIS 640×360 每秒 6 次。按时间发送帧，过期帧丢弃，禁止无限排队。', '',
            '| 项目 | 实测 |', '|---|---:|',
            f'| 回放时长 | {paced["duration_actual_s"]:.2f} s |',
            f'| 深度输出 | {paced["depth_count"]} 次 |',
            f'| 光流输出 | {paced["flow_count"]} 对 |',
            f'| 因来不及处理而丢弃的输入时隙 | {paced["dropped_source_ticks"]} |',
            f'| 平均 CPU 使用 | {paced["average_cpu_cores"]:.3f} 核（1 核额度的 {paced["average_1cpu_budget_utilization_pct"]:.1f}%） |',
            f'| 进程峰值 RSS | {paced["peak_process_rss_mib"]:.1f} MiB |',
            f'| 从计划输入时刻到结果就绪的 P95 | {paced["scheduled_frame_age_ms"]["p95"]:.1f} ms |', '',
            '19 秒素材循环时重置光流，避免跨片尾/片头计算虚假运动，因此光流次数会略少于 6×时长。这里的结果延迟不含摄像头到服务端的传输延迟。', '',
        ])
    else:
        lines.extend(['尚未完成组合回放；不能据单项计时声称组合负载可持续运行。', ''])
    checks = []
    for result in results:
        if result['kind'] == 'flow':
            check = result['validation']
            checks.append(f'- {result["profile"]} / {result["name"]}：已知平移的中位终点误差 {check["median_endpoint_error_px"]:.4f} px，静止图像光流 P95 {check["static_p95_magnitude_px"]:.4f} px。')
    lines.extend([
        '## 3. 验证与限制', '',
        '- 输入来自用户提供的 `compare-input-output.mp4`，仅裁取右半边 RGB，左半边已有深度效果不作为输入或真值。',
        '- 所有模型权重按固定 revision 下载，SHA256 与上游 LFS 元数据核对；未加载远端 Python 代码。',
        '- 深度输出检查二维形状、有限数值与非恒定输出；已查看预览。没有真实深度真值，未计算深度精度。',
        *checks,
        '- 合成平移只验证光流方向、单位及基本运行，不代表真实遮挡、反光和夜间条件的准确度。',
        '- 深度是相对量，不能报告“孩子距割草机器人 0.8 米”；不同模型、不同帧不能直接用原始值做距离差。',
        '- 输入中相机在移动，光流包含背景运动。云台旋转/变焦时应标记相机运动，再做背景补偿或暂停运动告警判断。',
        '- 这里只测单路文件输入；尚未测真实 SDK 连接、网络、H264 实时解码、多路竞争、服务器其他应用、VLM 或 T3 CPU 积分。', '',
        '## 4. 目前的实现选择', '',
        '下一版先用 DIS 做低成本运动特征和关键帧筛选；DepthART 448 作为每秒一次或事件触发的相对深度候选，资源紧张时试 224。Depth Anything V2 Small 保留为低频对照，当前默认尺寸的 CPU 时延不适合每帧处理。此选择只依据本次速度与效果观察，尚未证明准确率优于其他模型。', '',
        '儿童庭院活动、割草机器人、室内宠物/物品、门前包裹分别补拍固定机位、云台移动、遮挡、夜间片段，再验证业务判断。人物/宠物/机器人身份及告警含义需要检测、跟踪或 VLM；光流本身只描述像素变化。', '',
        'VLM 后续做同一批片段的 A/B 对照：RGB；RGB+深度；RGB+光流摘要；RGB+两者。记录误报、漏报、UNKNOWN、时延和费用，不能因增加两张辅助图就假定识别更准确。', '',
        '## 5. 查看效果和原始数据', '',
        '[DepthART 448 黑白深度预览](server-budget/depthart448-448/gray-preview-09.jpg) · [Depth Anything V2 黑白对照](server-budget/dav2small-518/gray-preview-09.jpg) · [DIS 光流预览](server-budget/dis/preview-056.jpg)', '',
        '![黑白深度：原图与三个模型](depth-grayscale-comparison.jpg)' if (folder / 'depth-grayscale-comparison.jpg').exists() else '', '',
        '**黑白与伪彩色来自同一份深度数值。** 黑白用亮暗表达相对远近，伪彩色使用颜色映射；换成黑白不需要另一套模型，也不会改变本次推理耗时或深度准确度。这里采用近亮远暗、每帧 2%–98% 分位归一化，不能从灰度直接换算米数。', '',
        '各方法目录中的 `result.json` 是汇总和环境证据，`samples.csv` 是逐帧数据，`depth-gray-*.png` 是单通道黑白图，`gray-preview-*.jpg` 是 RGB 与黑白深度对照，原 `preview-*.jpg` 保留伪彩色。`.npy` 原始浮点输出仅本地生成，未随本报告提交；原视频与抽帧输入由运行者自行提供。', '',
        '模型与算法来源、运行命令和接入建议见 [README](../../README.md)。', '',
    ])
    (folder / 'REPORT.md').write_text('\n'.join(lines), encoding='utf-8')
    print(folder / 'REPORT.md')


if __name__ == '__main__':
    main()
