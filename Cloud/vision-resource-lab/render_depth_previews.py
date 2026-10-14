"""Render grayscale from saved float32 predictions, without rerunning a model."""
from pathlib import Path
import argparse
import csv
import hashlib
import json

import cv2
import numpy as np
from PIL import Image

from benchmark import ROOT, gray_depth, labeled_panels, write_depth_previews


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    parser.add_argument('--raw-root', type=Path, default=ROOT)
    parser.add_argument('--inputs-root', type=Path, default=ROOT / 'inputs')
    args = parser.parse_args()
    fixture = json.loads((args.inputs_root / 'manifest.json').read_text())
    rendered = []
    comparison = {}
    for raw_file in sorted((args.raw_root / 'results' / args.run).glob('*/*/depth-*.npy')):
        index = int(raw_file.stem.split('-')[-1])
        with (raw_file.parent / 'samples.csv').open(newline='') as source:
            samples = list(csv.DictReader(source))
        time_s = float(samples[index]['time_s'])
        frame = min(fixture['frames'], key=lambda item: abs(item['time_s'] - time_s))
        if abs(frame['time_s'] - time_s) > 1e-5:
            raise ValueError('Cannot match depth prediction to its original RGB frame')
        bgr = cv2.imdecode(np.fromfile(args.inputs_root / frame['file'], dtype=np.uint8), cv2.IMREAD_COLOR)
        raw = np.load(raw_file, allow_pickle=False)
        if bgr is None or raw.ndim != 2 or not np.isfinite(raw).all():
            raise ValueError(f'Invalid source data: {raw_file}')
        model = json.loads((raw_file.parent / 'result.json').read_text())['args']['model']
        output = ROOT / 'results' / args.run / raw_file.parent.parent.name / raw_file.parent.name
        output.mkdir(parents=True, exist_ok=True)
        write_depth_previews(output, index, bgr, raw, model, time_s)
        image_path = output / f'depth-gray-{index:02d}.png'
        with Image.open(image_path) as image:
            if image.mode != 'L' or image.size != (bgr.shape[1], bgr.shape[0]):
                raise AssertionError('Expected a native-size single-channel grayscale PNG')
        digest = hashlib.sha256(raw_file.read_bytes()).hexdigest()
        rendered.append({'output': str(image_path.relative_to(ROOT)), 'model': model,
                         'sample_index': index, 'source_time_s': time_s,
                         'raw_float32_sha256': digest,
                         'normalization_percentiles_2_98': np.percentile(raw, [2, 98]).tolist()})
        if raw_file.parent.parent.name == 'server-budget' and index == 9:
            comparison[model] = gray_depth(raw, (bgr.shape[1], bgr.shape[0]))
            comparison['rgb'] = bgr
    if not rendered:
        raise RuntimeError('No saved depth .npy files found; run the benchmark first')
    if {'rgb', 'depthart224', 'depthart448', 'dav2small'} <= comparison.keys():
        gray_bgr = lambda name: cv2.cvtColor(comparison[name], cv2.COLOR_GRAY2BGR)
        top = labeled_panels([comparison['rgb'], gray_bgr('depthart448')], ['RGB | same source frame', 'DepthART 448 | grayscale'])
        bottom = labeled_panels([gray_bgr('depthart224'), gray_bgr('dav2small')], ['DepthART 224 | grayscale', 'Depth Anything V2 Small | grayscale'])
        cv2.imwrite(str(ROOT / 'results' / args.run / 'depth-grayscale-comparison.jpg'), np.vstack([top, bottom]))
    metadata = {'operation': 'display conversion only; no model inference or benchmark rerun',
                'grayscale': 'clip((raw-p2)/(p98-p2),0,1)*255, uint8; then bilinear resize',
                'interpretation': 'relative inverse-depth-like predictions: near bright, far dark; not metres',
                'source_video_sha256': fixture['source_sha256'], 'rendered': rendered}
    (ROOT / 'results' / args.run / 'depth-preview-rendering.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    print(f'Rendered {len(rendered)} single-channel grayscale PNGs and corresponding RGB/depth previews.')
    print('Model files, float32 predictions and benchmark measurements were not changed.')


if __name__ == '__main__':
    main()
