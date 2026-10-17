"""Deploy a reviewed demo runtime without replacing later cloud fixes or Web assets.

The release must contain runtime-audit.json captured from the active service and
a private venv installed from its requirements. Rollback changes code only.
"""
import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import subprocess

if __package__:
    from . import activate as legacy
else:
    import activate as legacy

DROPIN = Path('/etc/systemd/system/evidenceguard-demo.service.d/99-zzzzzzzz-vector-runtime.conf')


def current_args():
    pid = legacy.state(legacy.SERVICE, 'MainPID')
    return Path('/proc', pid, 'cmdline').read_bytes().decode().strip('\0').split('\0')


def configuration():
    paths = legacy.state(legacy.SERVICE, 'DropInPaths').split()
    paths += [legacy.state(legacy.SERVICE, 'FragmentPath'), '/etc/evidenceguard-demo/cloud.env']
    return {p:legacy.digest(Path(p)) for p in paths if p}


def audit_runtime(audit):
    active = audit['services']['evidenceguard-demo']
    if current_args() != active['args']:
        raise RuntimeError('Active demo runtime changed after audit')
    for name in ('evidenceguard-demo', 'evidenceguard', 'evidenceguard-review'):
        item = audit['services'][name]
        legacy.audit_source(Path(item['source']), item['files'])
    dropins = legacy.state(legacy.SERVICE, 'DropInPaths').split()
    if dropins != active['dropins'] or any(Path(p).name > DROPIN.name for p in dropins):
        raise RuntimeError('Systemd overrides changed or a later runtime exists')
    if configuration() != audit['configuration']:
        raise RuntimeError('Service configuration changed after audit')
    config = json.loads(legacy.CONFIG.read_text())
    if config['environments']['demo']['source'] != active['source'] + '/evidenceguard':
        raise RuntimeError('Collector source changed after audit')


def idle():
    with sqlite3.connect((legacy.DATA/'evidenceguard.sqlite3').as_uri()+'?mode=ro', uri=True) as db:
        active = db.execute("SELECT COUNT(*) FROM runs WHERE json_extract(payload,'$.status') IN ('queued','running','waiting')").fetchone()[0]
        indexing = db.execute("SELECT COUNT(*) FROM recordings WHERE json_extract(payload,'$.status') IN ('queued','indexing')").fetchone()[0]
        searching = db.execute("SELECT COUNT(*) FROM video_search_jobs WHERE json_extract(payload,'$.status') IN ('searching','verifying')").fetchone()[0] if db.execute("SELECT 1 FROM sqlite_master WHERE name='video_search_jobs'").fetchone() else 0
    if active or indexing or searching:
        raise RuntimeError('Demo has active Agent, indexing or retrieval jobs; retry after they finish')
    path=legacy.DATA/'evidenceguard-hardware.sqlite3'
    if path.exists():
        with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
            active=db.execute("SELECT COUNT(*) FROM records WHERE kind='operation' AND json_extract(body,'$.control')=1 AND json_extract(body,'$.executionState') IN ('queued','executing','verifying','unknown') AND COALESCE(json_extract(body,'$.leaseReleasedByHuman'),0)=0").fetchone()[0]
        if active: raise RuntimeError('Hardware control is running or unresolved; do not interrupt it')


def restore(backup):
    legacy.DROPIN = DROPIN
    legacy.restore(backup)


def activate(release):
    release, manifest = legacy.verify_release(release)
    audit = json.loads((release/'runtime-audit.json').read_text())
    audit_runtime(audit)
    python = release/'venv/bin/python'
    if not python.is_file():
        raise RuntimeError('Install release-local dependencies before activation')
    features=manifest.get('features',{})
    feature_lines=''
    if features:
        if features!={'localVision':True,'endpointProfile':'video','visualControl':True}:
            raise RuntimeError('Unknown runtime features')
        legacy.run(str(python),str(release/'vision_assets.py'),'--check')
        from importlib.util import spec_from_file_location,module_from_spec
        spec=spec_from_file_location('vision_assets',release/'vision_assets.py'); assets=module_from_spec(spec);spec.loader.exec_module(assets)
        feature_lines=(f'Environment=EG_LOCAL_VISION_ENABLED=1 EG_FLOW_ENABLED=1 EG_GUARD_AUX_ENABLED=1 EG_ENDPOINT_ENABLED=1 EG_ENDPOINT_PROFILE=video EG_VISUAL_CONTROL_ENABLED=1 EG_DEPTH_MODEL_PATH={assets.MODEL}\n')
    legacy.healthy()
    legacy.run(str(python), str(release/'preflight.py'))
    config = json.loads(legacy.CONFIG.read_text())
    observer = Path(config['reference']).parent
    import os
    legacy.run(str(python), str(observer/'compatibility.py'),
               env=dict(os.environ, PYTHONPATH=str(observer)+':'+str(release/'Cloud/server')), cwd='/tmp')
    audit_runtime(audit)
    idle()
    other = {s:legacy.state(s, 'MainPID') for s in ('evidenceguard', 'evidenceguard-review')}
    backup = legacy.BACKUPS/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup.mkdir(parents=True, mode=0o700)
    command = f'{release}/venv/bin/uvicorn eg_dashboard.bootstrap:app --app-dir {release}/Cloud/server --host 127.0.0.1 --port 8792 --proxy-headers --forwarded-allow-ips 127.0.0.1 --no-access-log'
    new = f"[Service]\nEnvironment=EG_PRODUCT_RELEASE={manifest['contentHash']}\nEnvironment=PYTHONPATH={release}/Cloud/dashboard\n{feature_lines}ExecStart=\nExecStart={command}\n"
    import hashlib
    saved = dict(release=str(release), contentHash=manifest['contentHash'],
        oldSource=config['environments']['demo']['source'], newSource=str(release/'Cloud/server/evidenceguard'),
        dropin=base64.b64encode(DROPIN.read_bytes()).decode() if DROPIN.exists() else None,
        dropinMode=DROPIN.stat().st_mode&0o777 if DROPIN.exists() else 0o644, configMode=legacy.CONFIG.stat().st_mode&0o777,
        newDropinHash=hashlib.sha256(new.encode()).hexdigest(), otherPids=other,
        originalExecStart=legacy.state(legacy.SERVICE, 'ExecStart'))
    (backup/'manifest.json').write_text(json.dumps(saved, indent=2))
    (backup/'collector-config.json').write_bytes(legacy.CONFIG.read_bytes())
    print('Rollback directory: '+str(backup), flush=True)
    written = False
    try:
        legacy.run('systemctl', 'stop', legacy.SERVICE)
        for name in ('evidenceguard.sqlite3', 'evidenceguard-hardware.sqlite3'):
            path = legacy.DATA/name
            if path.exists():
                with sqlite3.connect(path.as_uri()+'?mode=ro', uri=True) as source, sqlite3.connect(backup/name) as target:
                    source.backup(target)
                    if target.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                        raise RuntimeError('Database backup failed integrity check')
                (backup/name).chmod(0o600)
        DROPIN.write_text(new); DROPIN.chmod(0o644); written = True
        config['environments']['demo']['source'] = saved['newSource']
        legacy.CONFIG.write_text(json.dumps(config, ensure_ascii=False)); legacy.CONFIG.chmod(saved['configMode'])
        legacy.run('systemctl', 'daemon-reload')
        legacy.run('systemctl', 'start', legacy.SERVICE)
        legacy.healthy()
        if '--app-dir '+str(release/'Cloud/server')+' ' not in legacy.state(legacy.SERVICE, 'ExecStart'):
            raise RuntimeError('Systemd selected another runtime')
        legacy.run('systemctl', 'restart', legacy.COLLECTOR)
        if other != {s:legacy.state(s, 'MainPID') for s in other}:
            raise RuntimeError('Another environment changed during deployment')
        (backup/'activated.json').write_text(json.dumps(dict(release=str(release), contentHash=manifest['contentHash'])))
        print(json.dumps(dict(activation='passed', environment='demo', release=str(release),
                             backup=str(backup), contentHash=manifest['contentHash'], webAssets='preserved', otherServicesUnchanged=True)), flush=True)
    except BaseException:
        if written: restore(backup)
        else: legacy.run('systemctl', 'start', legacy.SERVICE)
        raise


if __name__ == '__main__':
    p=argparse.ArgumentParser(); g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--release', type=Path); g.add_argument('--rollback', type=Path)
    args=p.parse_args()
    if args.rollback: restore(args.rollback)
    else: activate(args.release)
