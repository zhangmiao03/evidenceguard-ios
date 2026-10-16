"""Transfer a demo-only archive through SSM, verify every chunk and final hash.

No activation here. The immutable release is staged next to the existing source.
Use cloud_command --resume after an uncertain SSM result; do not replay activation.
"""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import gzip
import io
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import tarfile

ROOT=Path(__file__).resolve().parents[2]


def upload(path, base_archive=None, base_release=None):
    raw=path.read_bytes(); full_digest=hashlib.sha256(raw).hexdigest()
    if bool(base_archive) != bool(base_release): raise ValueError('Both base archive and release are required')
    if base_release:
        if not re.fullmatch(r'/opt/evidenceguard-demo/releases/tools-[0-9a-f]{16}',base_release): raise ValueError('Invalid base release')
        with tarfile.open(base_archive,'r:gz') as previous:
            old=json.load(previous.extractfile('manifest.json'))['files']
        with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
            payload={m.name:archive.extractfile(m).read() for m in archive.getmembers() if m.isfile()}
        new=json.loads(payload['manifest.json'])['files']
        reduced={k:v for k,v in payload.items() if k=='manifest.json' or old.get(k)!=new.get(k)}
        buffer=io.BytesIO()
        with tarfile.open(fileobj=buffer,mode='w') as archive:
            for name,data in sorted(reduced.items()):
                member=tarfile.TarInfo(name);member.size=len(data);archive.addfile(member,io.BytesIO(data))
        raw=gzip.compress(buffer.getvalue(),mtime=0)
    digest=hashlib.sha256(raw).hexdigest()
    if len(raw)>20_000_000: raise ValueError('Release exceeds the reviewed 20 MB transfer limit')
    staging='/tmp/eg-demo-upload-'+digest[:16]
    release='/opt/evidenceguard-demo/releases/tools-'+full_digest[:16]
    with tempfile.TemporaryDirectory(prefix='eg-demo-upload-') as temp:
        def run(name,script):
            file=Path(temp)/(name+'.sh');file.write_text(script,encoding='utf-8',newline='\n')
            result=subprocess.run([sys.executable,str(ROOT/'scripts/cloud_command.py'),'--file',str(file),'--timeout','180'],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
            if result.returncode: raise RuntimeError(result.stderr+'\n'+result.stdout)
            return result.stdout.strip()
        run('prepare',f'set -eu\ninstall -d -m 700 {staging}\n')
        parts=[raw[i:i+18000] for i in range(0,len(raw),18000)]
        def part(item):
            index,data=item
            run('part-'+str(index),"python3 - <<'PY'\nimport base64,pathlib,hashlib\n"+
                f"data=base64.b64decode('{base64.b64encode(data).decode()}')\nassert hashlib.sha256(data).hexdigest()=='{hashlib.sha256(data).hexdigest()}'\npathlib.Path('{staging}/{index:05d}').write_bytes(data)\nPY\n")
            return index
        with ThreadPoolExecutor(max_workers=3) as pool:
            for done,_ in enumerate(pool.map(part,enumerate(parts)),1):
                if done%10==0 or done==len(parts): print(f'Verified {done}/{len(parts)} chunks',flush=True)
        script="python3 - <<'PY'\nimport pathlib,hashlib,io,tarfile,json,os\n"
        script+=f"staging=pathlib.Path('{staging}');release=pathlib.Path('{release}');data=b''.join((staging/f'{{i:05d}}').read_bytes() for i in range({len(parts)}))\nassert hashlib.sha256(data).hexdigest()=='{digest}'\n"
        script+=f"base={base_release!r}\n"
        script+="""with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
 members=archive.getmembers()
 assert len(members)<2000 and sum(m.size for m in members)<80_000_000
 assert len({m.name for m in members})==len(members)
 payload={}
 for m in members:
  assert m.isfile() and not m.name.startswith('/') and '..' not in pathlib.PurePosixPath(m.name).parts
  payload[m.name]=archive.extractfile(m).read()
 manifest=json.loads(payload['manifest.json'])
 assert manifest['environment']=='demo'
 for name in manifest['files']:
  assert not pathlib.PurePosixPath(name).is_absolute() and '..' not in pathlib.PurePosixPath(name).parts
  if name not in payload:
   assert base, 'Incomplete archive'
   source=pathlib.Path(base)/name
   assert source.resolve().is_relative_to(pathlib.Path(base).resolve())
   payload[name]=source.read_bytes()
 assert set(payload)==set(manifest['files'])|{'manifest.json'}
 for name,digest in manifest['files'].items(): assert hashlib.sha256(payload[name]).hexdigest()==digest
 assert hashlib.sha256(json.dumps(manifest['files'],sort_keys=True).encode()).hexdigest()==manifest['contentHash']
 if release.exists():
  for name,raw in payload.items(): assert (release/name).read_bytes()==raw,'Existing release differs'
 else:
  pending=release.with_name(release.name+'.pending')
  pending.mkdir(parents=True,exist_ok=False)
  for name,raw in payload.items():
   target=pending/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw);target.chmod(0o644)
  os.rename(pending,release)
 print(json.dumps({'release':str(release),'contentHash':manifest['contentHash'],'verifiedFiles':len(payload)}))
PY
"""
        print(run('assemble',script),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('archive',type=Path);p.add_argument('--base-archive',type=Path);p.add_argument('--base-release')
    args=p.parse_args();upload(args.archive,args.base_archive,args.base_release)
