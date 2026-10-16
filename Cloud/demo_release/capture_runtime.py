"""Read-only source/config hashes for the actually running demo, team and review.

Run on the server via SSM. Output contains hashes and process paths, never env
file contents, credentials or business records. Capture again before each deploy.
"""
import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path
import subprocess


def state(service, key):
    return subprocess.check_output(['systemctl','show',service,'--property='+key,'--value'],text=True).strip()


def inventory(root):
    result={};root=Path(root)
    for p in sorted(root.rglob('*')):
        rel=p.relative_to(root)
        source=rel.parts[0] in {'evidenceguard','tests'} and p.suffix in {'.py','.json'}
        prompt=p.suffix=='.md' and rel.parts[:3]==('evidenceguard','vision','prompts')
        if p.is_file() and '__pycache__' not in rel.parts and (source or prompt or rel.as_posix() in {'requirements.txt','migration_stage.py'}):
            result[rel.as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
    return result


def capture():
    result={'services':{}}
    for name in ('evidenceguard-demo','evidenceguard','evidenceguard-review'):
        pid=state(name,'MainPID')
        args=Path('/proc',pid,'cmdline').read_bytes().decode().strip('\0').split('\0')
        if '--app-dir' not in args:raise RuntimeError('Review unknown service command before deployment')
        source=args[args.index('--app-dir')+1]
        result['services'][name]=dict(source=source,args=args,files=inventory(source),dropins=state(name,'DropInPaths').split())
    paths=result['services']['evidenceguard-demo']['dropins']+[state('evidenceguard-demo','FragmentPath'),'/etc/evidenceguard-demo/cloud.env']
    result['configuration']={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths if p}
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--compressed',action='store_true');args=parser.parse_args()
    raw=json.dumps(capture(),sort_keys=True).encode()
    print(base64.b64encode(gzip.compress(raw)).decode() if args.compressed else raw.decode())
