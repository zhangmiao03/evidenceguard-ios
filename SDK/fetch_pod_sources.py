#!/usr/bin/env python3
"""Fetch build inputs for pinned public pods from their official Git trees.

Optional network workaround: avoids downloading every unrelated AWS service.
Requires an authenticated gh CLI. Credentials stay in memory and are not logged.
Every file is checked against its upstream Git blob ID before being archived.
"""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import time
import urllib.request

DEPENDENCIES = {
    'aws': ('aws-amplify/aws-sdk-ios', '2.41.0', '1b6c1a8658ae6f4dd1e194c6373faaf109718eb8',
            'aws-sdk-ios-2.41.0', ('AWSCore/', 'AWSIoT/'), {'AWSCore.podspec', 'AWSIoT.podspec', 'LICENSE'}),
    'sqlcipher': ('sqlcipher/sqlcipher', 'v4.5.4', 'c7f9a1c348fde215ac18ce2b78a62ce8111a3743',
                 'sqlcipher-v4.5.4', ('src/', 'ext/', 'tool/', 'config/'), None),
    'zip': ('ZipArchive/ZipArchive', '2.4.3', '38e0ce0598e06b034271f296a8e15b149c91aa19',
            'ZipArchive-2.4.3', ('SSZipArchive/',), {'LICENSE.txt', 'SSZipArchive.podspec', 'README.md'}),
}
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--dependency', choices=DEPENDENCIES, default='aws')
parser.add_argument('--cache', type=Path, default=Path(__file__).resolve().parent / '.tools/pod-archives')
args = parser.parse_args()
REPO, TAG, COMMIT, archive_name, prefixes, root_files = DEPENDENCIES[args.dependency]
cache = args.cache.resolve()
cache.mkdir(parents=True, exist_ok=True)
token = subprocess.check_output(['gh', 'auth', 'token'], text=True).strip()

def api(endpoint):
    for attempt in range(3):
        request = urllib.request.Request('https://api.github.com/repos/' + REPO + '/' + endpoint,
            headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                     'User-Agent': 'EvidenceGuard-SDK-Preparation', 'X-GitHub-Api-Version': '2022-11-28'})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except Exception:
            if attempt == 2:
                raise RuntimeError('Official source download failed; rerun to resume verified files.') from None
            time.sleep(1 + attempt)

ref = api('git/ref/tags/' + TAG)
if ref['object']['type'] == 'tag':
    ref = api('git/tags/' + ref['object']['sha'])
if ref['object']['sha'] != COMMIT or ref['object']['type'] != 'commit':
    raise SystemExit('Upstream tag differs from the verified commit; stop and review the dependency.')
tree = api('git/trees/' + COMMIT + '?recursive=1')
if tree.get('truncated'):
    raise SystemExit('Upstream tree was truncated; cannot verify the source set.')
files = [item for item in tree['tree'] if item['type'] == 'blob' and
         (item['path'].startswith(prefixes) or
          (item['path'] in root_files if root_files is not None else '/' not in item['path']))]
if not files or any(item.get('mode') not in {'100644', '100755'} for item in files):
    raise SystemExit('Unexpected source tree; refuse links or unsupported entries.')
objects = cache / 'verified-objects'
objects.mkdir(exist_ok=True)

def checked_blob(item):
    path = objects / item['sha']
    data = path.read_bytes() if path.exists() else base64.b64decode(api('git/blobs/' + item['sha'])['content'])
    digest = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    if digest != item['sha'] or len(data) != item['size']:
        raise RuntimeError('Source integrity check failed for ' + item['path'])
    path.write_bytes(data)
    return item, data

print(f'Verifying {len(files)} upstream {args.dependency} files…', flush=True)
verified = []
with ThreadPoolExecutor(max_workers=6) as executor:
    futures = [executor.submit(checked_blob, item) for item in files]
    for future in as_completed(futures):
        verified.append(future.result())
        if len(verified) % 30 == 0:
            print(f'Verified {len(verified)}/{len(files)} files', flush=True)
archive = cache / (archive_name + '.tgz')
temporary = archive.with_suffix('.partial')
with tarfile.open(temporary, 'w:gz') as output:
    for item, data in sorted(verified, key=lambda pair: pair[0]['path']):
        entry = tarfile.TarInfo(archive_name + '/' + item['path'])
        entry.size = len(data)
        entry.mode = int(item['mode'], 8) & 0o777
        output.addfile(entry, io.BytesIO(data))
temporary.replace(archive)
manifest = {'repository': REPO, 'commit': COMMIT, 'tree': tree['sha'],
            'files': len(verified), 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}
archive.with_suffix('.json').write_text(json.dumps(manifest, indent=2) + '\n')
print('Verified archive ready: ' + str(archive), flush=True)
