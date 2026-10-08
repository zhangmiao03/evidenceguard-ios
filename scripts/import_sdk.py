#!/usr/bin/env python3
"""Restore authorized SDK files from the organizer archive; never commit them."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def restore(archive: Path, web_only=False):
    count = 0
    total = 0
    digests = {}
    with zipfile.ZipFile(archive) as bundle:
        for entry in bundle.infolist():
            name = entry.filename
            if not entry.flag_bits & 0x800:
                try:
                    name = name.encode('cp437').decode('utf-8')
                except (UnicodeError, LookupError):
                    pass
            path = PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or '\\' in name:
                raise ValueError('SDK archive contains an unsafe path')
            if entry.is_dir() or '__MACOSX' in path.parts or path.name == '.DS_Store':
                continue
            if stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError('SDK archive contains a symbolic link')
            parts = path.parts
            destination = None
            if 'WebSDKDemo' in parts:
                relative = parts[parts.index('WebSDKDemo') + 1:]
                if relative[:2] == ('public', 'sdk'):
                    destination = ROOT/'Web'/'public'/Path(*relative[1:])
            if not web_only:
                for module in ('ESIotKit-DemoApp-iOS', 'ESIotKit-DemoApp-Common'):
                    if module in parts:
                        relative = parts[parts.index(module)+1:]
                        if not any(p in {'build', '.gradle', '.git', 'Pods', 'xcuserdata', 'node_modules'} for p in relative):
                            destination = ROOT/'SDK'/'Vendor'/module/Path(*relative)
            if destination is None:
                continue
            total += entry.file_size
            if entry.file_size > 1_000_000_000 or total > 5_000_000_000:
                raise ValueError('SDK archive exceeds the local import size limit')
            destination.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(entry) as source, destination.open('wb') as target:
                shutil.copyfileobj(source, target)
            if destination.name == 'gradlew':
                destination.chmod(0o755)
            if destination.name == 'index.js' and destination.parent.name == 'sdk':
                digests['webSDK'] = hashlib.sha256(destination.read_bytes()).hexdigest()
            count += 1
    if not (ROOT/'Web/public/sdk/index.js').exists():
        raise ValueError('Web SDK was not found in the supplied archive')
    (ROOT/'SDK').mkdir(exist_ok=True)
    (ROOT/'SDK/vendor-manifest.local.json').write_text(json.dumps({'files': count, 'bytes': total, 'digests': digests}, indent=2)+'\n')
    return count


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--web-only', action='store_true')
    args = parser.parse_args()
    print(f'Restored {restore(args.archive, args.web_only)} local SDK files. These files are ignored by Git.')
