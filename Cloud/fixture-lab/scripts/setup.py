"""Download a pinned upstream media server, verify digest, install isolated dependencies."""
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request

ROOT=Path(__file__).resolve().parent.parent
VERSION='v1.21.1'
for command in ('ffmpeg','npm'):
    if not shutil.which(command):
        raise SystemExit(f'Missing dependency: {command}')
system={'Darwin':'darwin','Linux':'linux'}.get(platform.system())
arch={'arm64':'arm64','aarch64':'arm64','x86_64':'amd64','AMD64':'amd64'}.get(platform.machine())
if not system or not arch:
    raise SystemExit('This launcher supports macOS/Linux arm64/amd64.')
runtime=ROOT/'.runtime'
runtime.mkdir(exist_ok=True)
if not (runtime/'mediamtx').exists():
    name=f'mediamtx_{VERSION}_{system}_{arch}.tar.gz'
    req=urllib.request.Request(f'https://api.github.com/repos/bluenviron/mediamtx/releases/tags/{VERSION}',headers={'User-Agent':'EvidenceGuard-setup'})
    metadata=json.load(urllib.request.urlopen(req,timeout=30))
    asset=next(a for a in metadata['assets'] if a['name']==name)
    digest=asset.get('digest','')
    if not digest.startswith('sha256:'):
        raise SystemExit('Upstream SHA256 metadata missing; refusing unchecked download.')
    content=urllib.request.urlopen(asset['browser_download_url'],timeout=90).read()
    if hashlib.sha256(content).hexdigest()!=digest.split(':')[1]:
        raise SystemExit('MediaMTX SHA256 mismatch')
    archive=runtime/name
    archive.write_bytes(content)
    with tarfile.open(archive) as tar:
        for filename in ('mediamtx','LICENSE'):
            entry=tar.getmember(filename)
            if not entry.isfile():
                raise SystemExit('Invalid archive')
            (runtime/filename).write_bytes(tar.extractfile(entry).read())
    (runtime/'mediamtx').chmod(0o755)
    (runtime/'upstream.json').write_text(json.dumps({'version':VERSION,'url':asset['browser_download_url'],'digest':digest},indent=2))
venv=ROOT/'.venv'
if not venv.exists():
    subprocess.run([sys.executable,'-m','venv',str(venv)],check=True)
python=str(venv/'bin'/'python')
if shutil.which('uv'):
    subprocess.run(['uv','pip','install','--python',python,'-r',str(ROOT/'requirements.lock')],check=True)
else:
    subprocess.run([python,'-m','pip','install','-r',str(ROOT/'requirements.lock')],check=True)
subprocess.run(['npm','ci'],cwd=ROOT/'frontend',check=True)
subprocess.run(['npm','run','build'],cwd=ROOT/'frontend',check=True)
print('Ready: .venv/bin/python scripts/run.py')
