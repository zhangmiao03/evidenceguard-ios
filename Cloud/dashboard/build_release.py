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
import zipfile

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
    website=io.BytesIO()
    with zipfile.ZipFile(website,'w',zipfile.ZIP_DEFLATED) as package:
        for p in sorted((ROOT/'Web/dist').rglob('*')):
            if p.is_file() and (p==index or p.parent.name=='assets'):
                package.writestr('dashboard/'+p.relative_to(ROOT/'Web/dist').as_posix(),p.read_bytes())
        package.writestr('index.html','<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=dashboard/index.html?view=showcase"><title>EvidenceGuard</title><a href="dashboard/index.html?view=showcase">打开 EvidenceGuard 作品</a></html>')
        package.writestr('README.txt',('EvidenceGuard competition website\nReference: '+revision+'\n\n'+
            'Upload the entire extracted folder to your static website root. Entry: /dashboard/index.html?view=showcase\n'+
            'Local preview: python -m http.server 8080 ; open http://127.0.0.1:8080/\n'+
            'The iOS preview is a browser interaction demo with synthetic, local-only state. It does not run native iOS or connect hardware.\n'+
            'Live monitoring needs the existing same-origin /dashboard/api proxy and the read-only collector.\n'+
            'On a static host, use the iOS demo or import a sanitized offline JSON export. No backend data or credentials are bundled.\n'+
            'Live URL: https://demo.47.131.21.137.sslip.io/dashboard?view=showcase\n'+
            'Backend deployment source and instructions: https://github.com/zhangmiao03/evidenceguard-ios/tree/dongrunze/Cloud/dashboard\n'))
    (output.parent/'evidenceguard-website.zip').write_bytes(website.getvalue())
    with tarfile.open(output,'w:gz') as archive:
        for p in sorted((ROOT/'Cloud/dashboard/eg_dashboard').glob('*.py')):
            put(archive,'eg_dashboard/'+p.name,p.read_bytes())
        put(archive,'eg_dashboard/_ops_runtime.py',(ROOT/'Cloud/server/evidenceguard/ops.py').read_bytes())
        put(archive,'capture_briefing.py',(ROOT/'Cloud/dashboard/capture_briefing.py').read_bytes())
        put(archive,'capture_skill_case.py',(ROOT/'Cloud/dashboard/capture_skill_case.py').read_bytes())
        put(archive,'verify_guard_replay.py',(ROOT/'Cloud/dashboard/verify_guard_replay.py').read_bytes())
        for name in ('trace_retention', 'display_receipts'):
            put(archive,'eg_dashboard/'+name+'.py',(ROOT/'Cloud/server/evidenceguard'/ (name+'.py')).read_bytes())
        put(archive,'web/downloads/evidenceguard-website.zip',website.getvalue())
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
