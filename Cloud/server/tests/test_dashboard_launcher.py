"""A developer shell cannot silently turn the local console into a production worker."""
import importlib.util
import os
from pathlib import Path
import sys

import pytest
import uvicorn


@pytest.mark.parametrize('explicit_config', [False, True])
def test_launcher_isolates_inherited_deployment_and_disables_senders(tmp_path, monkeypatch, explicit_config):
    script = Path(__file__).resolve().parents[3]/'scripts/run_dashboard.py'
    spec = importlib.util.spec_from_file_location('dashboard_launcher', script)
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    (tmp_path/'Web/dist').mkdir(parents=True)
    (tmp_path/'Web/dist/index.html').write_text('<html></html>')
    monkeypatch.setattr(launcher, 'ROOT', tmp_path)
    monkeypatch.setattr(os, 'environ', dict(os.environ, EG_ENV_FILE='/production.env',
        EG_DATABASE='/production.sqlite', EG_MODEL_API_KEY='inherited-production-key', EG_APNS_ENABLED='1'))
    args = ['run_dashboard.py']
    if explicit_config:
        config = tmp_path/'local.env'
        config.write_text('EG_MODEL_API_KEY=explicit-local-key\nEG_ENV_FILE=/other-production.env\nEG_APNS_ENABLED=1\nEG_DISABLE_WORKERS=0\n')
        args += ['--env-file', str(config)]
    monkeypatch.setattr(sys, 'argv', args)
    called = []
    monkeypatch.setattr(uvicorn, 'run', lambda *a, **kw: called.append(kw))
    launcher.main()
    assert 'EG_ENV_FILE' not in os.environ
    assert os.environ.get('EG_MODEL_API_KEY') == ('explicit-local-key' if explicit_config else None)
    assert os.environ['EG_DATABASE'] == str(tmp_path/'Cloud/data/local-dashboard/business.sqlite3')
    assert os.environ['EG_APNS_ENABLED'] == '0' and os.environ['EG_DISABLE_WORKERS'] == '1'
    assert called == [{'host': '127.0.0.1', 'port': 8790, 'workers': 1}]
