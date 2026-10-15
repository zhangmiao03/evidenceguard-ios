"""Package our observer and Dashboard only; never copy deployed business source.

Run after: npm run build --prefix Web -- --base /dashboard/
The embedded reference is hashes of committed repository files, not a claim that
the server has deployed that commit. Output lives in ignored Cloud/data.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[2]


def build(output, revision=None):
    revision = revision or subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if not __import__('re').fullmatch(r'[a-f0-9]{40}',revision):
        raise ValueError('Expected a full committed reference SHA')
    files = subprocess.check_output(['git','ls-tree','-r','--name-only',revision,'Cloud/server/evidenceguard'],cwd=ROOT,text=True).splitlines()
    hashes = {name.removeprefix('Cloud/server/evidenceguard/'):hashlib.sha256(subprocess.check_output(['git','show',revision+':'+name],cwd=ROOT)).hexdigest() for name in files if name.endswith('.py')}
    index=ROOT/'Web/dist/index.html'
    if not index.exists() or '/dashboard/assets/' not in index.read_text(encoding='utf-8'):
        raise RuntimeError('Build Web with --base /dashboard/ before packaging')
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    def put(archive,name,data):
        info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644
        archive.addfile(info,io.BytesIO(data))
    with tarfile.open(output,'w:gz') as archive:
        for p in sorted((ROOT/'Cloud/dashboard/eg_dashboard').glob('*.py')):
            put(archive,'eg_dashboard/'+p.name,p.read_bytes())
        put(archive,'eg_dashboard/_ops_runtime.py',(ROOT/'Cloud/server/evidenceguard/ops.py').read_bytes())
        for p in sorted((ROOT/'Web/dist').rglob('*')):
            # Deliberately exclude official SDK binaries, user files and media.
            if p.is_file() and (p==index or p.parent.name=='assets'):
                put(archive,'web/'+p.relative_to(ROOT/'Web/dist').as_posix(),p.read_bytes())
        for p in sorted((ROOT/'Cloud/dashboard/tests').glob('*.py')):
            put(archive,'tests/'+p.name,p.read_bytes())
        put(archive,'compatibility.py',(ROOT/'Cloud/dashboard/compatibility.py').read_bytes())
        put(archive,'activate.py',(ROOT/'Cloud/dashboard/activate.py').read_bytes())
        put(archive,'smoke_live.py',(ROOT/'Cloud/dashboard/smoke_live.py').read_bytes())
        put(archive,'reference.json',json.dumps({'revision':revision,'files':hashes},sort_keys=True).encode())
    digest=hashlib.sha256(output.read_bytes()).hexdigest()
    print(json.dumps({'path':str(output),'sha256':digest,'bytes':output.stat().st_size,'referenceRevision':revision}))
    return digest


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',default=str(ROOT/'Cloud/data/deploy/dashboard.tar.gz'));parser.add_argument('--reference')
    args=parser.parse_args();build(args.output,args.reference)
