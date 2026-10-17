"""Exercise rollback on fixture files; never contact systemd or real services."""
import base64
import importlib.util
import json
from pathlib import Path

import pytest

spec=importlib.util.spec_from_file_location('demo_activation',Path(__file__).with_name('activate.py'))
deploy=importlib.util.module_from_spec(spec);spec.loader.exec_module(deploy)


@pytest.fixture
def setup(tmp_path,monkeypatch):
    backups=tmp_path/'backups';backups.mkdir();backup=backups/'test';backup.mkdir()
    dropin=tmp_path/'50-tools.conf';dropin.write_text('new-code')
    config=tmp_path/'collector.json';config.write_text(json.dumps({'environments':{'demo':{'source':'new'},'team':{'source':'unchanged'},'review':{'source':'unchanged'}}}))
    database=tmp_path/'business.sqlite3';database.write_bytes(b'business writes made after deployment')
    (backup/'manifest.json').write_text(json.dumps({'release':'/opt/evidenceguard-demo/releases/tools-test','originalExecStart':'old-command','newDropinHash':deploy.digest(dropin),'dropin':None,'dropinMode':420,'configMode':420,'oldSource':'old','newSource':'new'}))
    calls=[]
    for key,value in {'BACKUPS':backups,'DROPIN':dropin,'CONFIG':config}.items():monkeypatch.setattr(deploy,key,value)
    monkeypatch.setattr(deploy,'run',lambda *args,**kwargs:calls.append(args))
    monkeypatch.setattr(deploy,'healthy',lambda **kwargs:None)
    monkeypatch.setattr(deploy,'state',lambda *args:'uvicorn --app-dir /opt/evidenceguard-demo/releases/tools-test/Cloud/server --port 8792')
    return backup,dropin,config,database,calls


@pytest.mark.parametrize('previous',[False,True])
def test_code_only_rollback_preserves_business_writes_and_other_environments(setup,previous):
    backup,dropin,config,database,calls=setup
    if previous:
        saved=json.loads((backup/'manifest.json').read_text());saved['dropin']=base64.b64encode(b'previous-code').decode();(backup/'manifest.json').write_text(json.dumps(saved))
    deploy.restore(backup)
    assert dropin.read_bytes()==b'previous-code' if previous else not dropin.exists()
    assert database.read_bytes()==b'business writes made after deployment'
    assert json.loads(config.read_text())['environments']=={'demo':{'source':'old'},'team':{'source':'unchanged'},'review':{'source':'unchanged'}}
    assert not any(call[-1] in {'evidenceguard','evidenceguard-review','nginx'} for call in calls)


def test_rollback_rejects_later_operator_edits_before_stopping_service(setup):
    backup,dropin,config,database,calls=setup
    dropin.write_text('later-operator-change')
    with pytest.raises(RuntimeError,match='changed'):deploy.restore(backup)
    assert calls==[] and dropin.read_text()=='later-operator-change'


def test_old_backup_cannot_override_newer_active_runtime(setup,monkeypatch):
    backup,dropin,config,database,calls=setup
    monkeypatch.setattr(deploy,'state',lambda *args:'uvicorn --app-dir /opt/evidenceguard-demo/releases/briefings/Cloud/server --port 8792')
    with pytest.raises(RuntimeError,match='Active runtime changed'):deploy.restore(backup)
    assert calls==[] and dropin.read_text()=='new-code'


def test_source_drift_is_detected_before_mutation(tmp_path):
    root=tmp_path/'source';(root/'evidenceguard').mkdir(parents=True)
    source=root/'evidenceguard/app.py';source.write_text('# audited')
    baseline={'evidenceguard/app.py':deploy.digest(source)}
    deploy.audit_source(root,baseline)
    source.write_text('# new cloud fix')
    with pytest.raises(RuntimeError,match='changed after audit'):deploy.audit_source(root,baseline)
