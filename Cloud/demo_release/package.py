"""Build a source-hashed demo release. Never package env files or business data."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[2]


def package(output, baseline):
    files = {}
    def add(path, name):
        if path.is_symlink(): raise ValueError('Symlink in release: ' + name)
        files[name] = path.read_bytes()
    server = ROOT/'Cloud/server'
    for path in sorted(server.rglob('*')):
        relative = path.relative_to(server)
        if path.is_file() and path.suffix in {'.py', '.json'} and relative.parts[0] in {'evidenceguard', 'tests'} and '__pycache__' not in relative.parts:
            add(path, 'Cloud/server/' + relative.as_posix())
    add(server/'requirements.txt', 'Cloud/server/requirements.txt')
    # Source-controlled synthetic fixtures are required by regression tests.
    # Never include runtime media folders or user/device images.
    fixtures=subprocess.check_output(['git','ls-files','-z','Cloud/server/evidenceguard/fixtures'],cwd=ROOT).decode().split('\0')
    for name in filter(None,fixtures):
        if Path(name).suffix not in {'.jpg','.png','.md'}: raise ValueError('Unexpected fixture type')
        add(ROOT/name,name)
    for name in ('run_dashboard.py', 'import_official_web_demo.py'):
        add(ROOT/'scripts'/name, 'scripts/' + name)
    for name in ('activate.py', 'preflight.py', 'smoke.py', 'web_release.py'):
        add(Path(__file__).parent/name, name)
    web = ROOT/'Web/dist'
    for required in ('index.html', 'sdk/index.js', 'sdk/manifest.local.json', 'official-demo/index.html', 'official-demo/manifest.json'):
        if not (web/required).is_file(): raise ValueError('Build product and official Web first: ' + required)
    for path in sorted(web.rglob('*')):
        if path.is_file():
            if path.suffix not in {'.js','.css','.html','.json','.svg','.png','.jpg','.jpeg','.webp','.wasm','.woff','.woff2','.ico'}:
                raise ValueError('Unexpected Web artifact: ' + str(path))
            add(path, 'web/' + path.relative_to(web).as_posix())
    # This is a file-hash inventory, never an environment/configuration dump.
    audit = json.loads(baseline.read_text(encoding='utf-8'))
    files['baseline.json'] = json.dumps({'demo':audit['remote']['demo'], 'team':audit['remote']['team']}, sort_keys=True).encode()
    manifest = {'schema':1, 'environment':'demo', 'baseRevision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'files':{k:hashlib.sha256(v).hexdigest() for k,v in files.items()}}
    manifest['contentHash'] = hashlib.sha256(json.dumps(manifest['files'],sort_keys=True).encode()).hexdigest()
    files['manifest.json'] = json.dumps(manifest,sort_keys=True,indent=2).encode()
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode='w') as archive:
        for name, data in sorted(files.items()):
            info = tarfile.TarInfo(name); info.size = len(data); info.mode = 0o644
            archive.addfile(info,io.BytesIO(data))
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes(gzip.compress(raw.getvalue(),mtime=0))
    print(json.dumps({'archive':str(output),'bytes':output.stat().st_size,'contentHash':manifest['contentHash'],
        'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'files':len(files)}))


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True)
    args=p.parse_args();package(args.output,args.baseline)
