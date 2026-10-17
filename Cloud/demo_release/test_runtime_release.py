import json
from pathlib import Path
import pytest

from Cloud.demo_release import runtime_release as runtime


def test_current_source_and_all_overrides_are_required(tmp_path,monkeypatch):
    config=tmp_path/'config.json';config.write_text(json.dumps({'environments':{'demo':{'source':'/current/evidenceguard'}}}))
    monkeypatch.setattr(runtime.legacy,'CONFIG',config)
    monkeypatch.setattr(runtime,'current_args',lambda:['current'])
    monkeypatch.setattr(runtime.legacy,'state',lambda *args:'/etc/90-current.conf')
    checked=[]
    monkeypatch.setattr(runtime.legacy,'audit_source',lambda p,h:checked.append(str(p)))
    audit={'services':{n:dict(source='/current',files={},args=['current'],dropins=['/etc/90-current.conf']) for n in ('evidenceguard-demo','evidenceguard','evidenceguard-review')}}
    audit['configuration']={'env-file':'hash'}
    monkeypatch.setattr(runtime,'configuration',lambda:dict(audit['configuration']))
    runtime.audit_runtime(audit)
    assert len(checked)==3
    monkeypatch.setattr(runtime,'current_args',lambda:['new-operator-release'])
    with pytest.raises(RuntimeError,match='changed'):runtime.audit_runtime(audit)
    monkeypatch.setattr(runtime,'current_args',lambda:['current'])
    monkeypatch.setattr(runtime.legacy,'state',lambda *args:'/etc/90-current.conf /etc/99-zzzzzzzzz-later.conf')
    with pytest.raises(RuntimeError,match='overrides'):runtime.audit_runtime(audit)


def test_runtime_rollback_uses_its_own_dropin_and_existing_code_only_restore(monkeypatch):
    calls=[]
    monkeypatch.setattr(runtime.legacy,'DROPIN',runtime.legacy.DROPIN)
    monkeypatch.setattr(runtime.legacy,'restore',lambda p:calls.append((p,runtime.legacy.DROPIN)))
    runtime.restore('backup')
    assert calls==[('backup',runtime.DROPIN)]


def test_idle_rejects_inflight_retrieval(tmp_path,monkeypatch):
    import sqlite3
    monkeypatch.setattr(runtime.legacy,'DATA',tmp_path)
    with sqlite3.connect(tmp_path/'evidenceguard.sqlite3') as db:
        for table in ('runs','recordings','video_search_jobs'):
            db.execute('CREATE TABLE '+table+' (payload TEXT)')
        db.execute('INSERT INTO video_search_jobs VALUES (?)',(json.dumps({'status':'verifying'}),))
    with pytest.raises(RuntimeError,match='retrieval'):runtime.idle()


def test_capture_includes_fixed_runtime_prompts_but_not_private_files(tmp_path):
    from Cloud.demo_release.capture_runtime import inventory
    prompt=tmp_path/'evidenceguard/vision/prompts/common.md';prompt.parent.mkdir(parents=True);prompt.write_text('rules')
    (tmp_path/'evidenceguard/private.env').write_text('secret')
    assert list(inventory(tmp_path))==['evidenceguard/vision/prompts/common.md']


def test_deploy_does_not_interrupt_unknown_hardware_control(tmp_path,monkeypatch):
    import sqlite3
    monkeypatch.setattr(runtime.legacy,'DATA',tmp_path)
    with sqlite3.connect(tmp_path/'evidenceguard.sqlite3') as db:
        for table in ('runs','recordings'):db.execute('CREATE TABLE '+table+' (payload TEXT)')
    with sqlite3.connect(tmp_path/'evidenceguard-hardware.sqlite3') as db:
        db.execute('CREATE TABLE records(kind TEXT,id TEXT,team TEXT,body TEXT)')
        db.execute('INSERT INTO records VALUES (?,?,?,?)',('operation','one','product',json.dumps({'control':True,'executionState':'unknown'})))
    with pytest.raises(RuntimeError,match='Hardware control'):runtime.idle()
    with sqlite3.connect(tmp_path/'evidenceguard-hardware.sqlite3') as db:
        db.execute('UPDATE records SET body=?',(json.dumps({'control':True,'executionState':'completed'}),))
    runtime.idle()
