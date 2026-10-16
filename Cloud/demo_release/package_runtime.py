"""Package tracked runtime/test sources; keep existing Web and private data intact."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parents[2]


def package(output,audit):
    files={}
    names=subprocess.check_output(['git','ls-files','-z','Cloud/server','Cloud/dashboard/eg_dashboard'],cwd=ROOT).decode().split('\0')
    names+=['scripts/'+n for n in ('check_sdk_host.py','run_dashboard.py','import_official_web_demo.py')]
    for name in filter(None,names):
        path=ROOT/name
        if path.is_symlink():raise ValueError('Symlinks are not packaged')
        if path.is_file() and path.suffix in {'.py','.json','.txt','.md','.png','.jpg'}:
            raw=path.read_bytes()
            files[name]=raw if path.suffix in {'.png','.jpg'} else raw.replace(b'\r\n',b'\n')
    for name in ('activate.py','preflight.py','runtime_release.py'):
        files[name]=(Path(__file__).parent/name).read_bytes().replace(b'\r\n',b'\n')
    snapshot=json.loads(audit.read_text(encoding='utf-8'))
    if not snapshot.get('configuration') or set(snapshot['services'])!={'evidenceguard-demo','evidenceguard','evidenceguard-review'}:
        raise ValueError('Capture current service inventory and configuration hashes first')
    files['runtime-audit.json']=json.dumps(snapshot,sort_keys=True).encode()
    manifest=dict(schema=1,environment='demo',baseRevision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        files={k:hashlib.sha256(v).hexdigest() for k,v in files.items()})
    manifest['contentHash']=hashlib.sha256(json.dumps(manifest['files'],sort_keys=True).encode()).hexdigest()
    files['manifest.json']=json.dumps(manifest,sort_keys=True,indent=2).encode()
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w') as archive:
        for name,data in sorted(files.items()):
            info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644
            archive.addfile(info,io.BytesIO(data))
    output.parent.mkdir(parents=True,exist_ok=True)
    raw=gzip.compress(stream.getvalue(),mtime=0);output.write_bytes(raw)
    print(json.dumps(dict(bytes=len(raw),files=len(files),sha256=hashlib.sha256(raw).hexdigest(),contentHash=manifest['contentHash'])))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--audit',type=Path,required=True)
    args=parser.parse_args();package(args.output,args.audit)
