"""CPU-only, cgroup-verified depth / classical optical-flow microbenchmark."""
from pathlib import Path
import argparse
import csv
import importlib.metadata
import json
import os
import platform
import resource
import time

import cv2
import numpy as np
import onnxruntime as ort
import psutil
from PIL import Image

ROOT = Path(__file__).resolve().parent
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def cgroup_state():
    relative = Path('/proc/self/cgroup').read_text().strip().split(':')[-1].lstrip('/')
    folder = Path('/sys/fs/cgroup') / relative
    values = {}
    for key in ['cpu.max', 'cpu.stat', 'memory.max', 'memory.current', 'memory.peak',
                'memory.swap.max', 'memory.events']:
        file = folder / key
        if file.exists():
            values[key] = file.read_text().strip()
    return {"path": str(folder), **values}


def stats(values):
    values = np.asarray(values, dtype=np.float64)
    return {"mean": float(values.mean()), "p50": float(np.median(values)),
            "p95": float(np.percentile(values, 95)), "min": float(values.min()),
            "max": float(values.max())}


def load_bgr(frame):
    # Filename is from our input manifest. imdecode handles Unicode Windows paths too.
    data = np.fromfile(ROOT / 'inputs' / frame['file'], dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"Invalid JPEG: {frame['file']}")
    return image


def normalized_tensor(bgr, model, resolution):
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    if model == 'dav2small':
        # Match this pinned HF DPTImageProcessor's minimal-change aspect ratio rule.
        height, width = rgb.shape[:2]
        sy, sx = resolution / height, resolution / width
        scale = sx if abs(1 - sx) < abs(1 - sy) else sy
        target = (max(14, round(width * scale / 14) * 14),
                  max(14, round(height * scale / 14) * 14))
        rgb = np.asarray(Image.fromarray(rgb).resize(target, Image.Resampling.BICUBIC))
    else:
        # DepthART's public infer_image.py uses square OpenCV cubic resizing.
        rgb = cv2.resize(rgb, (resolution, resolution), interpolation=cv2.INTER_CUBIC)
    tensor = (rgb.astype(np.float32) / 255.0 - MEAN) / STD
    return np.ascontiguousarray(tensor.transpose(2, 0, 1)[None])


def depth_gray_values(raw):
    # Visualization only: percentiles are per-frame, not calibrated metres.
    low, high = np.percentile(raw, [2, 98])
    scaled = np.clip((raw - low) / max(high - low, 1e-6), 0, 1)
    return np.uint8(scaled * 255)


def gray_depth(raw, size):
    return cv2.resize(depth_gray_values(raw), size, interpolation=cv2.INTER_LINEAR)


def color_depth(raw, size):
    gray = depth_gray_values(raw)
    return cv2.resize(cv2.applyColorMap(gray, cv2.COLORMAP_INFERNO), size,
                      interpolation=cv2.INTER_LINEAR)


def labeled_panels(panels, labels):
    width = 480
    height = 270
    output = []
    for img, label in zip(panels, labels):
        panel = cv2.resize(img, (width, height))
        header = np.full((42, width, 3), 24, np.uint8)
        cv2.putText(header, label, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, .60,
                    (240, 240, 240), 1, cv2.LINE_AA)
        output.append(np.vstack([header, panel]))
    return np.hstack(output)


def write_depth_previews(output, index, bgr, raw, model, time_s):
    size = (bgr.shape[1], bgr.shape[0])
    grayscale = gray_depth(raw, size)
    cv2.imwrite(str(output / f'depth-gray-{index:02d}.png'), grayscale)
    gray_preview = labeled_panels([bgr, cv2.cvtColor(grayscale, cv2.COLOR_GRAY2BGR)],
        [f'RGB | t={time_s:.2f}s', f'{model} | near bright, far dark'])
    cv2.imwrite(str(output / f'gray-preview-{index:02d}.jpg'), gray_preview)
    color_preview = labeled_panels([bgr, color_depth(raw, size)],
        [f'RGB | t={time_s:.2f}s', f'{model} | relative, NOT metres'])
    cv2.imwrite(str(output / f'preview-{index:02d}.jpg'), color_preview)


def run_depth(args, fixture, output):
    manifest = json.loads((ROOT / 'models' / 'manifest.json').read_text())
    options = ort.SessionOptions()
    options.intra_op_num_threads = args.threads
    options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.add_session_config_entry('session.intra_op.allow_spinning', '0')
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    begin = time.perf_counter()
    session = ort.InferenceSession(str(ROOT / 'models' / f'{args.model}.onnx'),
                                   sess_options=options, providers=['CPUExecutionProvider'])
    load_ms = (time.perf_counter() - begin) * 1000
    if session.get_providers() != ['CPUExecutionProvider']:
        raise RuntimeError('Benchmark must use CPU only')
    input_name = session.get_inputs()[0].name
    count = min(args.samples, len(fixture['frames']))
    selected = [fixture['frames'][i] for i in np.linspace(0, len(fixture['frames']) - 1, count, dtype=int)]
    warm_tensor = normalized_tensor(load_bgr(selected[0]), args.model, args.resolution)
    start = time.perf_counter()
    for _ in range(args.warmup):
        session.run(None, {input_name: warm_tensor})
    warmup_ms = (time.perf_counter() - start) * 1000
    records = []
    preview_indices = {count // 4, count // 2, 3 * count // 4}
    outputs_valid = True
    cpu_seconds = 0.0
    for i, frame in enumerate(selected):
        cpu_start = time.process_time()
        start = time.perf_counter()
        bgr = load_bgr(frame)
        decoded = time.perf_counter()
        tensor = normalized_tensor(bgr, args.model, args.resolution)
        preprocessed = time.perf_counter()
        raw = np.squeeze(session.run(None, {input_name: tensor})[0]).astype(np.float32)
        inferred = time.perf_counter()
        if raw.ndim != 2 or not np.isfinite(raw).all() or np.ptp(raw) <= 1e-6:
            outputs_valid = False
            raise RuntimeError('Depth output is invalid, nonfinite, or constant')
        # The canonical output is raw float32 at model resolution. Percentiles support
        # downstream descriptive facts. PNG resizing/saving is outside the timing.
        percentiles = np.percentile(raw, [2, 50, 98])
        finish = time.perf_counter()
        cpu_seconds += time.process_time() - cpu_start
        records.append({"index": i, "time_s": frame['time_s'],
                        "decode_ms": (decoded - start) * 1000,
                        "preprocess_ms": (preprocessed - decoded) * 1000,
                        "inference_ms": (inferred - preprocessed) * 1000,
                        "postprocess_ms": (finish - inferred) * 1000,
                        "pipeline_ms": (finish - start) * 1000})
        if i in preview_indices:
            np.save(output / f'depth-{i:02d}.npy', raw)
            write_depth_previews(output, i, bgr, raw, args.model, frame['time_s'])
        if i % 5 == 0 or i == count - 1:
            print(f'{args.model} {i+1}/{count}: {records[-1]["pipeline_ms"]:.1f} ms', flush=True)
    return records, {
        "model_artifact": manifest[args.model], "providers": session.get_providers(),
        "model_input": {"name": input_name, "declared_shape": session.get_inputs()[0].shape,
                        "actual_nchw": list(tensor.shape), "dtype": str(tensor.dtype)},
        "output_shape": list(raw.shape), "load_ms": load_ms, "warmup_ms": warmup_ms,
        "warmup_count": args.warmup, "outputs_finite_nonconstant": outputs_valid,
        "last_raw_percentiles_2_50_98": percentiles.tolist(),
        "timed_cpu_seconds": cpu_seconds,
        "meaning": "affine-invariant relative depth / disparity-like values, not metric distance",
        "timing_scope": "JPEG disk-read/decode + preprocessing + model + validity/percentile stats; excludes video decode, network, render/save, VLM and queue wait",
    }


def make_flow(algorithm):
    if algorithm == 'dis':
        return cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_FAST)
    return None


def calculate_flow(a, b, algorithm, engine):
    if algorithm == 'dis':
        return engine.calc(a, b, None)
    return cv2.calcOpticalFlowFarneback(a, b, None, .5, 3, 15, 3, 5, 1.2, 0)


def validate_flow(algorithm, engine):
    rng = np.random.default_rng(20261014)
    texture = rng.integers(0, 256, (240, 320), dtype=np.uint8)
    texture = cv2.GaussianBlur(texture, (5, 5), 1)
    dx, dy = 3.0, -2.0
    shifted = cv2.warpAffine(texture, np.float32([[1, 0, dx], [0, 1, dy]]),
                              (320, 240), borderMode=cv2.BORDER_REFLECT)
    flow = calculate_flow(texture, shifted, algorithm, engine)[20:-20, 20:-20]
    error = np.linalg.norm(flow - np.float32([dx, dy]), axis=2)
    static = calculate_flow(texture, texture, algorithm, engine)[20:-20, 20:-20]
    zero_error = np.linalg.norm(static, axis=2)
    result = {"known_translation_dx_dy": [dx, dy],
              "median_endpoint_error_px": float(np.median(error)),
              "static_p95_magnitude_px": float(np.percentile(zero_error, 95)),
              "scope": "synthetic sanity check only, not real-video ground truth"}
    if result['median_endpoint_error_px'] > 1.5 or result['static_p95_magnitude_px'] > .1:
        raise RuntimeError(f'Flow sanity validation failed: {result}')
    return result


def flow_frame(frame):
    bgr = load_bgr(frame)
    height = round(bgr.shape[0] * 640 / bgr.shape[1])
    bgr = cv2.resize(bgr, (640, height), interpolation=cv2.INTER_AREA)
    return bgr, cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)


def run_flow(args, fixture, output):
    engine = make_flow(args.algorithm)
    validation = validate_flow(args.algorithm, engine)
    rows = fixture['frames']
    _, previous = flow_frame(rows[0])
    _, second = flow_frame(rows[1])
    for _ in range(args.warmup):
        calculate_flow(previous, second, args.algorithm, engine)
    count = min(args.flow_pairs, len(rows) - 1)
    records = []
    cpu_seconds = 0.0
    for i in range(1, count + 1):
        cpu_start = time.process_time()
        start = time.perf_counter()
        bgr, current = flow_frame(rows[i])
        decoded = time.perf_counter()
        flow = calculate_flow(previous, current, args.algorithm, engine)
        computed = time.perf_counter()
        if not np.isfinite(flow).all():
            raise RuntimeError('Nonfinite optical flow')
        magnitude = np.linalg.norm(flow, axis=2)
        percentiles = np.percentile(magnitude, [50, 95])
        finish = time.perf_counter()
        cpu_seconds += time.process_time() - cpu_start
        records.append({"index": i, "time_s": rows[i]['time_s'],
                        "pair_dt_s": rows[i]['time_s'] - rows[i-1]['time_s'],
                        "decode_resize_gray_ms": (decoded - start) * 1000,
                        "flow_ms": (computed - decoded) * 1000,
                        "postprocess_ms": (finish - computed) * 1000,
                        "pipeline_ms": (finish - start) * 1000,
                        "median_magnitude_px_per_pair": float(percentiles[0]),
                        "p95_magnitude_px_per_pair": float(percentiles[1])})
        if i in {count // 4, count // 2, 3 * count // 4}:
            np.save(output / f'flow-{i:03d}.npy', flow)
            mag, angle = cv2.cartToPolar(flow[:, :, 0], flow[:, :, 1])
            hsv = np.zeros((*current.shape, 3), dtype=np.uint8)
            hsv[:, :, 0] = np.uint8(angle * 90 / np.pi) % 180
            hsv[:, :, 1] = 255
            hsv[:, :, 2] = np.uint8(np.clip(mag / 20.0, 0, 1) * 255)
            color = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
            arrows = bgr.copy()
            for y in range(16, current.shape[0], 24):
                for x in range(16, current.shape[1], 24):
                    vx, vy = flow[y, x]
                    if np.hypot(vx, vy) > 1:
                        end = (int(x + vx * 2), int(y + vy * 2))
                        cv2.arrowedLine(arrows, (x, y), end, (30, 220, 255), 1,
                                        cv2.LINE_AA, tipLength=.25)
            preview = labeled_panels([bgr, color, arrows],
                [f'RGB | t={rows[i]["time_s"]:.2f}s',
                 f'{args.algorithm}: hue=direction, value=speed', 'Arrows x2 | includes camera motion'])
            cv2.imwrite(str(output / f'preview-{i:03d}.jpg'), preview)
        previous = current
    print(f'{args.algorithm}: {count} frame pairs, sanity checks passed', flush=True)
    return records, {
        "algorithm": args.algorithm, "uses_learned_model": False,
        "flow_shape": list(flow.shape), "flow_units": "pixels per sampled frame pair",
        "nominal_pair_interval_s": rows[1]['time_s'] - rows[0]['time_s'],
        "timed_cpu_seconds": cpu_seconds, "validation": validation,
        "parameters": {"preset": "FAST"} if args.algorithm == 'dis' else
            {"pyr_scale": .5, "levels": 3, "winsize": 15, "iterations": 3, "poly_n": 5, "poly_sigma": 1.2},
        "timing_scope": "one JPEG decode + resize/gray + flow + magnitude stats, reuses previous grayscale; excludes first frame, H264 decode, network, preview/save and queue wait",
        "warning": "camera movement/rotation/zoom contributes to flow; this is not object speed or identity",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--kind', choices=['depth', 'flow'], required=True)
    parser.add_argument('--model', choices=['dav2small', 'depthart224', 'depthart448'], default='depthart224')
    parser.add_argument('--resolution', type=int, default=224)
    parser.add_argument('--algorithm', choices=['dis', 'farneback'], default='dis')
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--cpu-budget', type=float, required=True)
    parser.add_argument('--memory-gib', type=float, required=True)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--run', required=True)
    parser.add_argument('--samples', type=int, default=19)
    parser.add_argument('--flow-pairs', type=int, default=113)
    parser.add_argument('--warmup', type=int, default=2)
    args = parser.parse_args()
    if args.samples < 2 or args.flow_pairs < 2 or args.threads < 1:
        parser.error('Need >=2 samples/pairs and >=1 thread')
    cv2.setNumThreads(args.threads)
    cv2.ocl.setUseOpenCL(False)
    before = cgroup_state()
    quota, period = before['cpu.max'].split()
    if quota == 'max' or abs(int(quota) / int(period) - args.cpu_budget) > 1e-6:
        raise RuntimeError(f'CPU budget was not applied: {before}')
    if before['memory.max'] != str(int(args.memory_gib * 1024**3)) or before['memory.swap.max'] != '0':
        raise RuntimeError(f'Memory/swap budget was not applied: {before}')
    fixture = json.loads((ROOT / 'inputs' / 'manifest.json').read_text())
    name = f'{args.model}-{args.resolution}' if args.kind == 'depth' else args.algorithm
    output = ROOT / 'results' / args.run / args.profile / name
    output.mkdir(parents=True, exist_ok=True)
    print(f'{args.profile} / {name}: verified cpu.max={before["cpu.max"]}, memory.max={before["memory.max"]}', flush=True)
    start = time.perf_counter()
    records, details = (run_depth if args.kind == 'depth' else run_flow)(args, fixture, output)
    wall = time.perf_counter() - start
    metric_keys = [key for key in records[0] if key.endswith('_ms')]
    timings = {key: stats([row[key] for row in records]) for key in metric_keys}
    measured_seconds = sum(row['pipeline_ms'] for row in records) / 1000
    mean_cpu_cores = details['timed_cpu_seconds'] / measured_seconds
    process = psutil.Process()
    result = {
        "name": name, "kind": args.kind, "profile": args.profile, "args": vars(args),
        "platform": platform.platform(), "python": platform.python_version(),
        "packages": {package: importlib.metadata.version(package) for package in
                     ['numpy', 'opencv-python-headless', 'onnxruntime', 'psutil', 'Pillow']},
        "cpu_model": next((line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines()
                           if line.startswith('model name')), 'unknown'),
        "logical_cpus_visible": os.cpu_count(),
        "cpu_affinity_visible": process.cpu_affinity(),
        "note": "WSL host resource quota, not AWS EC2 performance simulation",
        "cgroup_before": before, "cgroup_after": cgroup_state(),
        "peak_process_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        "final_process_rss_mib": process.memory_info().rss / 1024**2,
        "sample_count": len(records), "timings_ms": timings,
        "continuous_pipeline_throughput_per_s": 1000 / timings['pipeline_ms']['mean'],
        "mean_cpu_cores_during_timed_pipeline": mean_cpu_cores,
        "average_cpu_budget_utilization_pct": 100 * mean_cpu_cores / args.cpu_budget,
        "process_wall_s_including_load_warmup_preview": wall,
        "fixture": {k: v for k, v in fixture.items() if k != 'frames'},
        **details,
    }
    (output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    with (output / 'samples.csv').open('w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    print(f'Finished {name}: p50={timings["pipeline_ms"]["p50"]:.1f} ms, '
          f'p95={timings["pipeline_ms"]["p95"]:.1f} ms, peak RSS={result["peak_process_rss_mib"]:.1f} MiB', flush=True)


if __name__ == '__main__':
    main()
