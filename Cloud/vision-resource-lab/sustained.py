"""Paced, single-camera replay: DIS 6 Hz + relative depth 1 Hz, bounded backlog."""
import argparse
import csv
import json
import resource
import time

import cv2
import numpy as np
import onnxruntime as ort
import psutil

from benchmark import ROOT, cgroup_state, load_bgr, normalized_tensor, stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=int, default=60)
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if args.seconds < 10:
        parser.error('Use at least 10 seconds')
    before = cgroup_state()
    if before['cpu.max'] != '100000 100000' or before['memory.max'] != '2147483648' or before['memory.swap.max'] != '0':
        raise RuntimeError('Expected 1 CPU / 2 GiB / no swap cgroup')
    cv2.setNumThreads(1)
    cv2.ocl.setUseOpenCL(False)
    fixture = json.loads((ROOT / 'inputs' / 'manifest.json').read_text())
    if fixture['sample_fps_requested'] != 6:
        raise RuntimeError('This paced test requires prepare_input.py --sample-fps 6')
    frames = fixture['frames']
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.add_session_config_entry('session.intra_op.allow_spinning', '0')
    session = ort.InferenceSession(str(ROOT / 'models' / 'depthart448.onnx'), sess_options=options,
                                   providers=['CPUExecutionProvider'])
    name = session.get_inputs()[0].name
    session.run(None, {name: normalized_tensor(load_bgr(frames[0]), 'depthart448', 448)})
    flow_engine = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_FAST)
    output = ROOT / 'results' / args.run / 'sustained-1cpu-2g'
    output.mkdir(parents=True, exist_ok=False)
    process = psutil.Process()
    previous = None
    previous_index = None
    last_depth_slot = -1
    tick = 0
    dropped_ticks = 0
    depth_count = 0
    flow_count = 0
    records = []
    cpu_start = time.process_time()
    started = time.perf_counter()
    next_progress = 10
    while True:
        elapsed = time.perf_counter() - started
        if elapsed >= args.seconds:
            break
        newest_tick = int(elapsed * 6)
        if newest_tick > tick:
            dropped_ticks += newest_tick - tick
            tick = newest_tick
        due = started + tick / 6
        if due >= started + args.seconds:
            break
        time.sleep(max(0, due - time.perf_counter()))
        frame_index = tick % len(frames)
        start = time.perf_counter()
        bgr = load_bgr(frames[frame_index])
        resized = cv2.resize(bgr, (640, round(bgr.shape[0] * 640 / bgr.shape[1])), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        # Replay discontinuities are not motion. Never flow across the loop boundary.
        if previous is not None and previous_index < frame_index:
            flow = flow_engine.calc(previous, gray, None)
            if not np.isfinite(flow).all():
                raise RuntimeError('Invalid flow')
            _ = np.percentile(np.linalg.norm(flow, axis=2), [50, 95])
            flow_count += 1
        previous, previous_index = gray, frame_index
        run_depth = tick // 6 != last_depth_slot
        if run_depth:
            depth = np.squeeze(session.run(None, {name: normalized_tensor(bgr, 'depthart448', 448)})[0])
            if not np.isfinite(depth).all() or np.ptp(depth) < 1e-6:
                raise RuntimeError('Invalid depth')
            _ = np.percentile(depth, [2, 50, 98])
            depth_count += 1
            last_depth_slot = tick // 6
        finish = time.perf_counter()
        records.append({"tick": tick, "source_frame_index": frame_index,
                        "elapsed_s": start - started, "depth_ran": run_depth,
                        "processing_ms": (finish - start) * 1000,
                        "scheduled_frame_age_ms": (finish - due) * 1000,
                        "rss_mib": process.memory_info().rss / 1024**2})
        tick += 1
        if finish - started >= next_progress:
            print(f'{int(finish-started)}s: depth={depth_count}, flow={flow_count}, dropped_ticks={dropped_ticks}', flush=True)
            next_progress += 10
    elapsed = time.perf_counter() - started
    cpu_seconds = time.process_time() - cpu_start
    result = {
        "duration_requested_s": args.seconds, "duration_actual_s": elapsed,
        "target_depth_hz": 1, "target_flow_hz": 6,
        "depth_count": depth_count, "flow_count": flow_count,
        "processed_ticks": len(records), "dropped_source_ticks": dropped_ticks,
        "flow_note": "one missing flow pair at each 19-second video-loop boundary is intentional",
        "frame_processing_ms": stats([row['processing_ms'] for row in records]),
        "scheduled_frame_age_ms": stats([row['scheduled_frame_age_ms'] for row in records]),
        "peak_process_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        "final_process_rss_mib": process.memory_info().rss / 1024**2,
        "cpu_seconds": cpu_seconds,
        "average_cpu_cores": cpu_seconds / elapsed,
        "average_1cpu_budget_utilization_pct": 100 * cpu_seconds / elapsed,
        "cgroup_before": before, "cgroup_after": cgroup_state(),
        "pipeline": "one CPU process; DepthART MNv4-M-slim-SPF 448 + DIS FAST 640x360; JPEG decode; latest-frame scheduling",
        "scope": "local file replay, not live H264 decode, network, backend, VLM, multiple cameras, EC2 CPU-credit or long-duration stability test",
    }
    (output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    with (output / 'samples.csv').open('w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
