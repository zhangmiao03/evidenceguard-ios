"""Make an explicit, reproducible JPEG-frame fixture from a local video."""
from pathlib import Path
import argparse
import hashlib
import json
import cv2

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--crop", choices=["right-half", "full"], default="full")
    parser.add_argument("--sample-fps", type=float, default=6)
    args = parser.parse_args()
    if args.sample_fps <= 0:
        parser.error("sample-fps must be positive")
    cv2.setNumThreads(1)
    source = cv2.VideoCapture(str(args.video))
    if not source.isOpened():
        raise RuntimeError(f"Cannot open {args.video}")
    fps = source.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        raise RuntimeError("Video must have a known positive frame rate")
    width, height = (int(source.get(k)) for k in [cv2.CAP_PROP_FRAME_WIDTH, cv2.CAP_PROP_FRAME_HEIGHT])
    folder = ROOT / "inputs"
    folder.mkdir(exist_ok=True)
    rows = []
    index = 0
    sample = 0
    while True:
        ok, frame = source.read()
        if not ok:
            break
        if index >= round(sample * fps / min(fps, args.sample_fps)):
            if args.crop == "right-half":
                frame = frame[:, width // 2:]
            filename = f"rgb-{index:06d}.jpg"
            if not cv2.imwrite(str(folder / filename), frame, [cv2.IMWRITE_JPEG_QUALITY, 95]):
                raise RuntimeError(f"Cannot write {filename}")
            rows.append({"file": filename, "source_frame": index, "time_s": index / fps})
            sample += 1
        index += 1
    source.release()
    digest = hashlib.file_digest(args.video.open("rb"), 'sha256').hexdigest()
    metadata = {
        "source_name": args.video.name, "source_sha256": digest,
        "source_width": width, "source_height": height, "source_fps": fps,
        "decoded_frames": index, "crop": args.crop,
        "crop_xywh": [width // 2, 0, width - width // 2, height] if args.crop == "right-half" else [0, 0, width, height],
        "sample_fps_requested": args.sample_fps, "jpeg_quality": 95,
        "timestamps": "source frame index / FPS, not a wall-clock camera timestamp",
        "frames": rows,
    }
    (folder / "manifest.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in metadata.items() if k != 'frames'}, indent=2))
    print(f"Prepared {len(rows)} JPEG frames")


if __name__ == "__main__":
    main()
