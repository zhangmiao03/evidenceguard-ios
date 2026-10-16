import importlib.util
import json
from pathlib import Path
import sys
import pytest

sys.path.insert(0,str(Path(__file__).parent))
import runtime_release as runtime


def test_current_source_and_all_overrides_are_required(tmp_path,monkeypatch):
    config=tmp_path/'config.json';config.write_text(json.dumps({'environments':{'demo':{'source':'/current/evidenceguard'}}}))
    monkeypatch.setattr(runtime.legacy,'CONFIG',config)
    monkeypatch.setattr(runtime,'current_args',lambda:['current'])
    monkeypatch.setattr(runtime.legacy,'state',lambda *args:'/etc/90-current.conf')
    checked=[]
    monkeypatch.setattr(runtime.legacy,'audit_source',lambda p,h:checked.append(str(p)))
    audit={'services':{n:dict(source='/current',files={},args=['current'],dropins=['/etc/90-current.conf']) for n in ('evidenceguard-demo','evidenceguard','evidenceguard-review')}}
    runtime.audit_runtime(audit)
    assert len(checked)==3
    monkeypatch.setattr(runtime,'current_args',lambda:['new-operator-release'])
    with pytest.raises(RuntimeError,match='changed'):runtime.audit_runtime(audit)
    monkeypatch.setattr(runtime,'current_args',lambda:['current'])
    monkeypatch.setattr(runtime.legacy,'state',lambda *args:'/etc/90-current.conf /etc/99-zzzzzzzzz-later.conf')
    with pytest.raises(RuntimeError,match='overrides'):runtime.audit_runtime(audit)


def test_runtime_rollback_uses_its_own_dropin_and_existing_code_only_restore(monkeypatch):
    calls=[]
    monkeypatch.setattr(runtime.legacy,'restore',lambda p:calls.append((p,runtime.legacy.DROPIN)))
    runtime.restore('backup')
    assert calls==[('backup',runtime.DROPIN)]
