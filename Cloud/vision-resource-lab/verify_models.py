"""Offline SHA256/size validation of the model artifacts used in the report."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parent


def main():
    folder = ROOT / 'models'
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    failed = False
    for name, expected in manifest.items():
        path = folder / f'{name}.onnx'
        if not path.exists():
            print(f'MISSING {path.name}: run git lfs pull')
            failed = True
            continue
        with path.open('rb') as src:
            prefix = src.read(80)
            src.seek(0)
            digest = hashlib.file_digest(src, 'sha256').hexdigest()
        if prefix.startswith(b'version https://git-lfs.github.com/spec/v1'):
            print(f'LFS POINTER ONLY {path.name}: run git lfs pull')
            failed = True
            continue
        ok = path.stat().st_size == expected['bytes'] and digest == expected['sha256']
        print(f'{"OK" if ok else "MISMATCH"} {path.name} {path.stat().st_size} bytes SHA256={digest}')
        failed |= not ok
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
