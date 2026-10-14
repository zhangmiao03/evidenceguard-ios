"""Restore the organizer's browser SDK locally. No credentials or binaries in Git."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('sdk_directory', type=Path, help='官方 WebSDKDemo/public/sdk 目录')
args = parser.parse_args()
source = args.sdk_directory.resolve()
entry = source / 'index.js'
if not entry.is_file():
    parser.error('目录中缺少 index.js')
target = Path(__file__).resolve().parents[1] / 'Web/public/sdk'
target.mkdir(parents=True, exist_ok=True)
shutil.copy2(entry, target / 'index.js')
if (source / 'i18n').is_dir():
    shutil.copytree(source / 'i18n', target / 'i18n', dirs_exist_ok=True)
(target / 'manifest.local.json').write_text(json.dumps({'sha256': hashlib.sha256(entry.read_bytes()).hexdigest(), 'bytes': entry.stat().st_size}, indent=2), encoding='utf-8')
print('Web SDK restored to ignored Web/public/sdk; no account credentials were read.')
