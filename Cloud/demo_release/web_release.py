"""Switch only demo static Web; preserve the already deployed backend and data.

Requires the active runtime to match the package's application/requirements
hashes. Code/config drift aborts before a restart. Rollback restores only this
Web override and collector's demo source, never databases or other environments.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import urllib.request

if __package__:
    from . import activate as common
else:
    import activate as common

DROPIN = Path('/etc/systemd/system/evidenceguard-demo.service.d/80-demo-web.conf')
BACKUPS = Path('/var/backups/evidenceguard-demo-web')
ENV_FILE = Path('/etc/evidenceguard-demo/cloud.env')


def source():
    pid = common.state(common.SERVICE, 'MainPID')
    args = Path('/proc/' + pid + '/cmdline').read_bytes().decode().strip('\0').split('\0')
    return Path(args[args.index('--app-dir') + 1]).resolve()


def configuration():
    paths = common.state(common.SERVICE, 'DropInPaths').split()
    paths.append(common.state(common.SERVICE, 'FragmentPath'))
    paths.append(str(ENV_FILE))
    return {p: common.digest(Path(p)) for p in paths if p and Path(p) != DROPIN}


def runtime_hashes(root):
    result = {'requirements.txt': common.digest(root / 'requirements.txt')}
    for p in sorted((root / 'evidenceguard').rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts and (p.suffix in {'.py', '.json'} or common.runtime_prompt(p.relative_to(root))):
            result[p.relative_to(root).as_posix()] = common.digest(p)
    return result


def verify_runtime(root, manifest):
    prefix = 'Cloud/server/'
    expected = {p[len(prefix):]: h for p, h in manifest['files'].items()
                if p == prefix + 'requirements.txt' or p.startswith(prefix + 'evidenceguard/') and
                (Path(p).suffix in {'.py', '.json'} or common.runtime_prompt(Path(p[len(prefix):])))}
    if runtime_hashes(root) != expected:
        raise RuntimeError('Active backend differs from the reviewed package; recompare before Web deployment')


def idle():
    with sqlite3.connect((common.DATA / 'evidenceguard.sqlite3').as_uri() + '?mode=ro', uri=True) as db:
        if db.execute("SELECT COUNT(*) FROM runs WHERE json_extract(payload,'$.status') IN ('queued','running','waiting')").fetchone()[0]:
            raise RuntimeError('Active Agent runs; retry after completion')
    hardware = common.DATA / 'evidenceguard-hardware.sqlite3'
    if hardware.exists():
        with sqlite3.connect(hardware.as_uri() + '?mode=ro', uri=True) as db:
            if db.execute("SELECT COUNT(*) FROM records WHERE kind='operation' AND json_extract(body,'$.executionState') IN ('queued','awaitingApproval','executing','verifying')").fetchone()[0]:
                raise RuntimeError('Active hardware operations; retry after completion')


def atomic_write(path, data, mode):
    pending = path.with_name(path.name + '.pending')
    with pending.open('xb') as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    pending.chmod(mode)
    os.replace(pending, path)


def collector_source(expected, replacement, mode):
    # Re-read immediately before writing so unrelated dashboard changes survive.
    current = json.loads(common.CONFIG.read_text(encoding='utf-8'))
    if current['environments']['demo']['source'] not in expected:
        raise RuntimeError('Collector source changed; review before replacing it')
    current['environments']['demo']['source'] = replacement
    atomic_write(common.CONFIG, json.dumps(current, ensure_ascii=False).encode(), mode)


def restore(directory):
    directory = Path(directory).resolve()
    if directory.parent != BACKUPS:
        raise ValueError('Unexpected Web backup directory')
    saved = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    if configuration() != saved['configuration'] or runtime_hashes(Path(saved['source'])) != saved['runtime']:
        raise RuntimeError('Backend configuration/source changed; old Web backup cannot override it')
    if not DROPIN.exists() or common.digest(DROPIN) != saved['newDropinHash']:
        raise RuntimeError('Web override changed; review before rollback')
    current = json.loads(common.CONFIG.read_text(encoding='utf-8'))
    if current['environments']['demo']['source'] not in {saved['oldCollector'], saved['newCollector']}:
        raise RuntimeError('Collector source changed; review before rollback')
    idle()
    common.run('systemctl', 'stop', common.SERVICE)
    if saved['dropin'] is None:
        DROPIN.unlink()
    else:
        atomic_write(DROPIN, base64.b64decode(saved['dropin']), saved['dropinMode'])
    collector_source({saved['oldCollector'], saved['newCollector']}, saved['oldCollector'], saved['configMode'])
    common.run('systemctl', 'daemon-reload')
    common.run('systemctl', 'start', common.SERVICE)
    common.healthy(web=True)
    if source().as_posix() != saved['source']:
        raise RuntimeError('Unexpected backend after Web rollback')
    common.run('systemctl', 'restart', common.COLLECTOR)
    print(json.dumps(dict(webRollback='passed', backup=str(directory), businessData='preserved')))


def activate(release):
    release, manifest = common.verify_release(release)
    root = source()
    verify_runtime(root, manifest)
    common.healthy(web=True)
    later = [p for p in common.state(common.SERVICE, 'DropInPaths').split() if Path(p).name > DROPIN.name]
    if later:
        raise RuntimeError('Later overrides exist; review them before Web deployment')
    configuration_before = configuration()
    other = {s: common.state(s, 'MainPID') for s in ('evidenceguard', 'evidenceguard-review')}
    config = json.loads(common.CONFIG.read_text(encoding='utf-8'))
    new = f'[Service]\nEnvironment=EG_WEB_ROOT={release}/web\n'.encode()
    backup = BACKUPS / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup.mkdir(parents=True, mode=0o700)
    backup.chmod(0o700)
    saved = dict(source=root.as_posix(), runtime=runtime_hashes(root), configuration=configuration_before,
                 release=str(release), newDropinHash=hashlib.sha256(new).hexdigest(),
                 dropin=base64.b64encode(DROPIN.read_bytes()).decode() if DROPIN.exists() else None,
                 dropinMode=DROPIN.stat().st_mode & 0o777 if DROPIN.exists() else 0o644,
                 oldCollector=config['environments']['demo']['source'], newCollector=str(root / 'evidenceguard'),
                 configMode=common.CONFIG.stat().st_mode & 0o777, otherPids=other)
    (backup / 'manifest.json').write_text(json.dumps(saved, indent=2), encoding='utf-8')
    (backup / 'collector-config.json').write_bytes(common.CONFIG.read_bytes())
    idle()
    if source() != root or configuration() != configuration_before:
        raise RuntimeError('Deployment changed during preflight')
    verify_runtime(root, manifest)
    print('Web rollback directory: ' + str(backup), flush=True)
    written = False
    try:
        common.run('systemctl', 'stop', common.SERVICE)
        atomic_write(DROPIN, new, 0o644)
        written = True
        collector_source({saved['oldCollector']}, saved['newCollector'], saved['configMode'])
        common.run('systemctl', 'daemon-reload')
        common.run('systemctl', 'start', common.SERVICE)
        common.healthy(web=True)
        if source() != root:
            raise RuntimeError('Backend source changed during Web deployment')
        with urllib.request.urlopen('http://127.0.0.1:8792/', timeout=10) as response:
            if hashlib.sha256(response.read()).hexdigest() != manifest['files']['web/index.html']:
                raise RuntimeError('New Web entry is not being served')
        common.run('systemctl', 'restart', common.COLLECTOR)
        if other != {s: common.state(s, 'MainPID') for s in other}:
            raise RuntimeError('Another environment changed during deployment')
        result = dict(webDeployment='passed', release=str(release), backend=root.as_posix(),
                      backup=str(backup), otherServicesUnchanged=True, businessData='preserved')
        (backup / 'activated.json').write_text(json.dumps(result))
        print(json.dumps(result), flush=True)
    except BaseException:
        if written:
            restore(backup)
        else:
            common.run('systemctl', 'start', common.SERVICE)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--release', type=Path)
    group.add_argument('--rollback', type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise RuntimeError('Run through the authorized demo maintenance session')
    restore(args.rollback) if args.rollback else activate(args.release)
