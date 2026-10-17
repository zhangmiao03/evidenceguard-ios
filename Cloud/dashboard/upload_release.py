"""Upload a locally built observer archive through existing SSM permissions.

Only transfers the explicitly supplied local package to the fixed project EC2.
Checks every part and the final SHA-256 before extracting regular files into a
new content-addressed release. Does not activate or restart services.
"""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]


def upload(path, no_system_proxy=False):
    raw=Path(path).read_bytes();digest=hashlib.sha256(raw).hexdigest()
    # Native anker artwork is bundled in both the web tree and the website ZIP.
    # Keep a bounded transfer while allowing these reviewed static assets.
    if len(raw)>5_000_000:raise ValueError('Observer archive is unexpectedly large')
    staging='/tmp/eg-dashboard-upload-'+digest[:16]
    release='/opt/evidenceguard-dashboard/releases/'+digest[:16]
    with tempfile.TemporaryDirectory(prefix='eg-upload-') as temp:
        def run(name,script):
            p=Path(temp)/(name+'.sh');p.write_text(script,encoding='utf-8',newline='\n')
            command=[sys.executable,str(ROOT/'scripts/cloud_command.py'),'--file',str(p),'--timeout','180']
            if no_system_proxy:command.append('--no-system-proxy')
            result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
            if result.returncode:raise RuntimeError(result.stderr+'\n'+result.stdout)
            return result.stdout.strip()
        print(run('prepare',f"set -eu\ninstall -d -m 700 {staging}\n"),flush=True)
        parts=[raw[i:i+18000] for i in range(0,len(raw),18000)]
        def part(item):
            index,data=item;encoded=base64.b64encode(data).decode()
            script="python3 - <<'PY'\nimport base64,pathlib,hashlib\n"
            script+=f"data=base64.b64decode('{encoded}')\nassert hashlib.sha256(data).hexdigest()=='{hashlib.sha256(data).hexdigest()}'\npathlib.Path('{staging}/{index:04d}').write_bytes(data)\nprint('part {index+1}/{len(parts)} verified')\nPY\n"
            return run('part-'+str(index),script)
        with ThreadPoolExecutor(max_workers=3) as pool:
            for output in pool.map(part,enumerate(parts)):print(output,flush=True)
        script="python3 - <<'PY'\nimport pathlib,hashlib,io,tarfile,json\n"
        script+=f"staging=pathlib.Path('{staging}'); release=pathlib.Path('{release}')\ndata=b''.join((staging/f'{{i:04d}}').read_bytes() for i in range({len(parts)}))\nassert hashlib.sha256(data).hexdigest()=='{digest}'\nrelease.mkdir(parents=True,exist_ok=True)\n"
        script+="with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:\n for member in archive:\n  assert member.isfile(), 'Only regular files allowed'\n  target=(release/member.name).resolve()\n  assert target.is_relative_to(release.resolve()) and not target.is_symlink()\n  target.parent.mkdir(parents=True,exist_ok=True)\n  target.write_bytes(archive.extractfile(member).read()); target.chmod(0o644)\n"
        script+=f"print(json.dumps({{'release':str(release),'sha256':'{digest}','bytes':len(data)}}))\nPY\n"
        print(run('assemble',script),flush=True)
    return release


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('archive',type=Path)
    parser.add_argument('--no-system-proxy',action='store_true')
    args=parser.parse_args();upload(args.archive,args.no_system_proxy)
