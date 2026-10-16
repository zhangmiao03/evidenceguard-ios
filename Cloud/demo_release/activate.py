"""Demo-only release activation with source drift checks and code-only rollback.

Original code, credentials, recordings and databases stay in place. Backups are
server-private. Normal rollback preserves all business writes made after deploy.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import urllib.request
import urllib.error

BASE=Path('/opt/evidenceguard-demo/releases')
BACKUPS=Path('/var/backups/evidenceguard-demo-tools')
SOURCE=Path('/opt/evidenceguard-demo/Cloud/server')
DATA=Path('/var/lib/evidenceguard-demo')
DROPIN=Path('/etc/systemd/system/evidenceguard-demo.service.d/50-demo-tools.conf')
CONFIG=Path('/etc/evidenceguard-dashboard/config.json')
SERVICE='evidenceguard-demo'
COLLECTOR='evidenceguard-dashboard-collector'
VENV=Path('/opt/evidenceguard-demo/venv-build10')


def run(*args, **kwargs): return subprocess.run(list(args),check=True,text=True,**kwargs)
def state(name, key): return subprocess.check_output(['systemctl','show',name,'--property='+key,'--value'],text=True).strip()
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def runtime_prompt(relative):
    return relative.suffix == '.md' and relative.parts[:3] == ('evidenceguard','vision','prompts')


def verify_release(release):
    release=Path(release).resolve()
    if release.parent!=BASE or not release.name.startswith('tools-'): raise ValueError('Only demo releases are accepted')
    manifest=json.loads((release/'manifest.json').read_text())
    if manifest['environment']!='demo': raise ValueError('Wrong environment')
    for name, expected in manifest['files'].items():
        target=(release/name).resolve()
        if not target.is_relative_to(release) or digest(target)!=expected: raise ValueError('Release integrity failure: '+name)
    return release,manifest


def audit_source(root, expected):
    actual={}
    for path in root.rglob('*'):
        relative=path.relative_to(root)
        if path.is_file() and '__pycache__' not in relative.parts and (relative.as_posix() in {'requirements.txt','requirements-vision.txt','migration_stage.py'} or
            relative.parts[0] in {'evidenceguard','tests'} and path.suffix in {'.py','.json'} or runtime_prompt(relative)):
            actual[relative.as_posix()]=digest(path)
    if actual!=expected: raise RuntimeError('Cloud source changed after audit; recompare before deployment: '+str(root))


def healthy(web=False):
    for _ in range(40):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8792/api/health',timeout=2) as r:
                assert r.status==200
            try: urllib.request.urlopen('http://127.0.0.1:8792/api/bootstrap',timeout=2)
            except urllib.error.HTTPError as error:
                if error.code!=401: raise RuntimeError('Authentication changed') from error
            else: raise RuntimeError('Missing API authentication')
            if web:
                for path in ('/','/sdk/manifest.local.json','/official-demo/index.html','/official-demo/manifest.json'):
                    with urllib.request.urlopen('http://127.0.0.1:8792'+path,timeout=3) as r: assert r.status==200
            return
        except (urllib.error.URLError,ConnectionError,TimeoutError): time.sleep(.5)
    raise RuntimeError('Demo health did not recover')


def restore(directory):
    directory=Path(directory).resolve()
    if directory.parent!=BACKUPS: raise ValueError('Unexpected backup directory')
    saved=json.loads((directory/'manifest.json').read_text())
    # Do not overwrite a later operator's unrelated deployment/configuration edits.
    command=state(SERVICE,'ExecStart')
    expected_app_dir=(Path(saved['release'])/'Cloud/server').as_posix()
    if command!=saved['originalExecStart'] and '--app-dir '+expected_app_dir+' ' not in command:
        raise RuntimeError('Active runtime changed since deployment; old backup cannot roll back a later release')
    if DROPIN.exists() and digest(DROPIN)!=saved['newDropinHash']:
        raise RuntimeError('Demo drop-in changed since deployment; review before rollback')
    current=json.loads(CONFIG.read_text())
    if current['environments']['demo']['source'] not in {saved['newSource'],saved['oldSource']}:
        raise RuntimeError('Collector demo source changed since deployment')
    run('systemctl','stop',SERVICE)
    if saved['dropin'] is None: DROPIN.unlink(missing_ok=True)
    else: DROPIN.write_bytes(base64.b64decode(saved['dropin']));DROPIN.chmod(saved['dropinMode'])
    current['environments']['demo']['source']=saved['oldSource']
    CONFIG.write_text(json.dumps(current,ensure_ascii=False));CONFIG.chmod(saved['configMode'])
    run('systemctl','daemon-reload');run('systemctl','start',SERVICE);healthy()
    run('systemctl','restart',COLLECTOR)
    print(json.dumps({'rollback':'passed','backup':str(directory),'databaseRestored':False,'businessWrites':'preserved'}),flush=True)


def activate(release, preflight=True):
    release,manifest=verify_release(release)
    baseline=json.loads((release/'baseline.json').read_text())
    audit_source(SOURCE,baseline['demo'])
    audit_source(Path('/opt/evidenceguard/Cloud/server'),baseline['team'])
    healthy()
    command=state(SERVICE,'ExecStart')
    if str(VENV) not in command or 'eg_dashboard.bootstrap:app' not in command:
        raise RuntimeError('Unreviewed service command; do not replace it')
    later=[p for p in state(SERVICE,'DropInPaths').split() if Path(p).name>DROPIN.name]
    if later:
        raise RuntimeError('Later systemd overrides exist; review the active runtime before deploying: '+', '.join(later))
    other={s:state(s,'MainPID') for s in ('evidenceguard','evidenceguard-review')}
    config=json.loads(CONFIG.read_text())
    observer=Path(config['reference']).parent
    if preflight:
        run(str(VENV/'bin/python'),str(release/'preflight.py'))
        run(str(VENV/'bin/python'),str(observer/'compatibility.py'),env=dict(os.environ,PYTHONPATH=str(observer)+':'+str(release/'Cloud/server')),cwd='/tmp')
    # Check again after tests. A deploy may not interrupt an Agent run.
    audit_source(SOURCE,baseline['demo'])
    with sqlite3.connect((DATA/'evidenceguard.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
        active=db.execute("SELECT COUNT(*) FROM runs WHERE json_extract(payload,'$.status') IN ('queued','running','waiting')").fetchone()[0]
        if active: raise RuntimeError('Demo has active Agent runs; retry after completion')
    backup=BACKUPS/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup.mkdir(parents=True,mode=0o700);backup.chmod(0o700)
    new=f'''[Service]
Environment=EG_WEB_ROOT={release}/web
Environment=EG_PRODUCT_RELEASE={manifest['contentHash']}
ExecStart=
ExecStart={VENV}/bin/uvicorn eg_dashboard.bootstrap:app --app-dir {release}/Cloud/server --host 127.0.0.1 --port 8792 --proxy-headers --forwarded-allow-ips 127.0.0.1 --no-access-log
'''
    saved={'release':str(release),'contentHash':manifest['contentHash'],'oldSource':config['environments']['demo']['source'],
        'newSource':str(release/'Cloud/server/evidenceguard'),'dropin':base64.b64encode(DROPIN.read_bytes()).decode() if DROPIN.exists() else None,
        'dropinMode':DROPIN.stat().st_mode&0o777 if DROPIN.exists() else 0o644,'configMode':CONFIG.stat().st_mode&0o777,
        'newDropinHash':hashlib.sha256(new.encode()).hexdigest(),'otherPids':other,'originalExecStart':command}
    (backup/'manifest.json').write_text(json.dumps(saved,indent=2));(backup/'collector-config.json').write_bytes(CONFIG.read_bytes())
    print('Rollback directory: '+str(backup),flush=True)
    try:
        run('systemctl','stop',SERVICE)
        for name in ('evidenceguard.sqlite3','evidenceguard-hardware.sqlite3'):
            path=DATA/name
            if path.exists():
                with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as source, sqlite3.connect(backup/name) as target:
                    source.backup(target)
                    if target.execute('PRAGMA quick_check').fetchone()[0]!='ok': raise RuntimeError('Backup validation failed')
                (backup/name).chmod(0o600)
        DROPIN.parent.mkdir(parents=True,exist_ok=True);DROPIN.write_text(new);DROPIN.chmod(0o644)
        config['environments']['demo']['source']=saved['newSource']
        CONFIG.write_text(json.dumps(config,ensure_ascii=False));CONFIG.chmod(saved['configMode'])
        run('systemctl','daemon-reload')
        if '--app-dir '+str(release/'Cloud/server')+' ' not in state(SERVICE,'ExecStart'):
            raise RuntimeError('Systemd did not select the intended release')
        run('systemctl','start',SERVICE);healthy(web=True)
        run('systemctl','restart',COLLECTOR)
        if other!={s:state(s,'MainPID') for s in other}: raise RuntimeError('Another environment changed during deployment')
        (backup/'activated.json').write_text(json.dumps({'pid':state(SERVICE,'MainPID'),'release':str(release),'contentHash':manifest['contentHash']}))
        print(json.dumps({'activation':'passed','environment':'demo','release':str(release),'contentHash':manifest['contentHash'],'backup':str(backup),'otherServicesUnchanged':True}),flush=True)
    except BaseException:
        # Before writing the drop-in, the previous value is already the rollback target.
        if DROPIN.exists() and digest(DROPIN)!=saved['newDropinHash'] and saved['dropin'] is not None and DROPIN.read_bytes()==base64.b64decode(saved['dropin']):
            run('systemctl','start',SERVICE)
        else: restore(backup)
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True);g.add_argument('--release',type=Path);g.add_argument('--rollback',type=Path)
    args=p.parse_args()
    if os.geteuid()!=0: raise RuntimeError('Run with the authorized root SSM maintenance command')
    if args.rollback: restore(args.rollback)
    else: activate(args.release)
