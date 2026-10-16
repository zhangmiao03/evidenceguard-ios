"""Web-only rollout must preserve a newer backend and all business writes."""
import base64
import json

import pytest

from Cloud.demo_release import web_release as deploy


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    root = tmp_path / 'backend'
    (root / 'evidenceguard').mkdir(parents=True)
    (root / 'requirements.txt').write_text('same-dependencies')
    (root / 'evidenceguard/app.py').write_text('# new cloud fix')
    backups = tmp_path / 'backups'
    backups.mkdir()
    dropin = tmp_path / '80-demo-web.conf'
    config = tmp_path / 'collector.json'
    config.write_text(json.dumps(dict(environments=dict(demo=dict(source='old-source'), team=dict(source='team-source')), capture=dict(policy='unchanged'))))
    database = tmp_path / 'business.sqlite3'
    database.write_bytes(b'new writes must survive rollback')
    calls = []
    monkeypatch.setattr(deploy, 'BACKUPS', backups)
    monkeypatch.setattr(deploy, 'DROPIN', dropin)
    monkeypatch.setattr(deploy.common, 'CONFIG', config)
    monkeypatch.setattr(deploy, 'source', lambda: root)
    monkeypatch.setattr(deploy, 'configuration', lambda: {'backend-override': 'unchanged'})
    monkeypatch.setattr(deploy, 'idle', lambda: None)
    monkeypatch.setattr(deploy.common, 'healthy', lambda **kwargs: None)
    monkeypatch.setattr(deploy.common, 'run', lambda *args: calls.append(args))
    monkeypatch.setattr(deploy.common, 'state', lambda service, key: '' if key == 'DropInPaths' else '123')
    return root, backups, dropin, config, database, calls


def backup(fixture, previous=None):
    root, backups, dropin, config, _, _ = fixture
    directory = backups / 'test'
    directory.mkdir()
    dropin.write_bytes(b'new web')
    saved = dict(source=root.as_posix(), runtime=deploy.runtime_hashes(root),
                 configuration=deploy.configuration(), newDropinHash=deploy.common.digest(dropin),
                 dropin=base64.b64encode(previous).decode() if previous else None, dropinMode=0o644,
                 oldCollector='old-source', newCollector=str(root / 'evidenceguard'), configMode=0o644)
    (directory / 'manifest.json').write_text(json.dumps(saved))
    return directory


@pytest.mark.parametrize('previous', [None, b'previous web'])
def test_rollback_restores_only_web_and_demo_collector(fixture, previous):
    root, _, dropin, config, database, calls = fixture
    directory = backup(fixture, previous)
    # An unrelated collector change made after deployment must survive rollback.
    value = json.loads(config.read_text(encoding='utf-8'))
    value['capture']['policy'] = 'later capture fix'
    config.write_text(json.dumps(value))
    deploy.restore(directory)
    assert dropin.read_bytes() == previous if previous else not dropin.exists()
    assert json.loads(config.read_text(encoding='utf-8'))['capture']['policy'] == 'later capture fix'
    assert json.loads(config.read_text(encoding='utf-8'))['environments']['team']['source'] == 'team-source'
    assert database.read_bytes() == b'new writes must survive rollback'
    assert (root / 'evidenceguard/app.py').read_text() == '# new cloud fix'
    assert not any(call[-1] in {'evidenceguard', 'evidenceguard-review', 'nginx'} for call in calls)


@pytest.mark.parametrize('changed', ['backend', 'configuration', 'web', 'collector'])
def test_rollback_rejects_later_operator_changes_before_restart(fixture, monkeypatch, changed):
    root, _, dropin, config, _, calls = fixture
    directory = backup(fixture)
    if changed == 'backend': (root / 'evidenceguard/app.py').write_text('# later fix')
    if changed == 'configuration': monkeypatch.setattr(deploy, 'configuration', lambda: {'backend-override': 'new'})
    if changed == 'web': dropin.write_text('later web')
    if changed == 'collector':
        value = json.loads(config.read_text(encoding='utf-8')); value['environments']['demo']['source'] = 'another-release'
        config.write_text(json.dumps(value))
    with pytest.raises(RuntimeError): deploy.restore(directory)
    assert calls == []


def test_active_backend_must_match_package(fixture):
    root, _, _, _, _, _ = fixture
    manifest = dict(files={'Cloud/server/' + name: digest for name, digest in deploy.runtime_hashes(root).items()})
    deploy.verify_runtime(root, manifest)
    (root / 'evidenceguard/new_fix.py').write_text('# must preserve')
    with pytest.raises(RuntimeError, match='differs'): deploy.verify_runtime(root, manifest)


def test_failed_web_health_automatically_restores_old_config(fixture, monkeypatch):
    root, backups, dropin, config, database, calls = fixture
    manifest = dict(files={'Cloud/server/' + name: digest for name, digest in deploy.runtime_hashes(root).items()})
    monkeypatch.setattr(deploy.common, 'verify_release', lambda release: (root.parent / 'release', manifest))
    count = 0
    def health(**kwargs):
        nonlocal count
        count += 1
        if count == 2: raise RuntimeError('injected health failure')
    monkeypatch.setattr(deploy.common, 'healthy', health)
    with pytest.raises(RuntimeError, match='injected'): deploy.activate(root.parent / 'release')
    assert not dropin.exists()
    assert json.loads(config.read_text(encoding='utf-8'))['environments']['demo']['source'] == 'old-source'
    assert database.read_bytes() == b'new writes must survive rollback'
    assert len(list(backups.iterdir())) == 1
    assert count == 3
