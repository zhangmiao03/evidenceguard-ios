import copy
import importlib.util
import json
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.staticfiles import StaticFiles

from evidenceguard.access import TeamAccess
from evidenceguard.camera import official_demo


def vision_request():
    return {'model': official_demo.OFFICIAL_AI_MODEL, 'max_tokens': 1024,
            'messages': [{'role': 'user', 'content': [
                {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,aW1hZ2U='}},
                {'type': 'text', 'text': '检查本次画面'},
            ]}]}


def test_official_static_shell_does_not_open_proxy_or_other_api(tmp_path, monkeypatch):
    monkeypatch.setenv('EG_WEB_ROOT', str(tmp_path))
    (tmp_path/'official-demo').mkdir()
    (tmp_path/'official-demo/index.html').write_text('official host')
    app = FastAPI()
    app.add_middleware(TeamAccess, token='a'*40)
    official_demo.install_official_demo_routes(app)
    app.mount('/', StaticFiles(directory=tmp_path))
    with TestClient(app) as client:
        assert client.get('/official-demo/index.html').status_code == 200
        assert client.post('/official-demo/index.html').status_code == 401
        assert client.get('/official-demo/../private.txt').status_code == 401
        assert client.post('/api/sdk/official-ai/chat/completions', json=vision_request()).status_code == 401
        assert client.get('/api/devices').status_code == 401


def test_official_ai_fixed_target_server_only_key_and_no_debug_fields(monkeypatch):
    app = FastAPI()
    official_demo.install_official_demo_routes(app)
    monkeypatch.delenv('EG_OFFICIAL_AI_KEY', raising=False)
    with TestClient(app) as client:
        assert client.post('/api/sdk/official-ai/chat/completions', json=vision_request()).status_code == 503
        monkeypatch.setenv('EG_OFFICIAL_AI_KEY', 'server-only-test-key')
        calls = []
        class Upstream:
            def __init__(self, **kwargs):
                assert kwargs['follow_redirects'] is False
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def post(self, url, **kwargs):
                calls.append((url, kwargs))
                return httpx.Response(200, json={'choices': [{'message': {'content': '十帧观察'}}],
                                                'debug': 'server-only-test-key'})
        monkeypatch.setattr(official_demo.httpx, 'AsyncClient', Upstream)
        result = client.post('/api/sdk/official-ai/chat/completions', json=vision_request(),
                             headers={'Authorization': 'Bearer browser-team-token'})
        assert result.status_code == 200 and '十帧观察' in result.text
        assert 'server-only-test-key' not in result.text and 'debug' not in result.text
        assert calls[0][0] == official_demo.OFFICIAL_AI_URL
        assert calls[0][1]['headers'] == {'Authorization': 'Bearer server-only-test-key'}
        assert client.post('/api/sdk/official-ai/chat/completions', content=b'x').status_code == 422
        assert client.post('/api/sdk/official-ai/chat/completions', content=b'x'*20_000_001).status_code == 413
        assert len(calls) == 1


@pytest.mark.parametrize('change', ['url', 'model', 'role', 'tool', 'eleven', 'empty', 'bad-type'])
def test_official_ai_rejects_non_demo_requests(change):
    data = copy.deepcopy(vision_request())
    if change == 'url': data['messages'][0]['content'][0]['image_url']['url'] = 'http://127.0.0.1/private'
    if change == 'model': data['model'] = 'arbitrary-model'
    if change == 'role': data['messages'][0]['role'] = 'system'
    if change == 'tool': data['tools'] = [{}]
    if change == 'eleven': data['messages'][0]['content'] = [data['messages'][0]['content'][0]]*11 + [data['messages'][0]['content'][1]]
    if change == 'empty': data['messages'][0]['content'] = []
    if change == 'bad-type': data = []
    with pytest.raises(HTTPException) as error:
        official_demo.validate_demo_request(data)
    assert error.value.status_code == 422


def test_demo_import_keeps_ui_and_ignores_env_and_credentials(tmp_path):
    script = Path(__file__).resolve().parents[3]/'scripts/import_official_web_demo.py'
    spec = importlib.util.spec_from_file_location('import_official_demo', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source, target = tmp_path/'source', tmp_path/'restored'
    for relative in ['src/App.tsx', 'src/components/LivePanel.tsx', 'src/components/AIRawFramePanel.tsx', 'src/utils/load-sdk.ts']:
        file = source/relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text('// original source\n')
    config = ("export const DEFAULT_AUTH_CONFIG: AuthConfig = {\n" +
              ''.join(f"  {key}: '',\n" for key in ['appName', 'clientId', 'clientSecret', 'presetKey', 'stationSn', 'eufyUserId', 'accountUuid']) +
              "};\nconst STORAGE_KEY = 'eufy-web-sdk-demo-auth-config';\nlocalStorage.setItem('secret', 'value');")
    (source/'src/config.ts').write_text(config)
    (source/'.env').write_text('private-test-value')
    (source/'src/private.json').write_text('{"private":true}')
    module.restore(source, target)
    assert (target/'src/App.tsx').read_bytes() == (source/'src/App.tsx').read_bytes()
    assert 'localStorage' not in (target/'src/config.ts').read_text()
    assert not (target/'.env').exists() and not (target/'src/private.json').exists()
    assert json.loads((target/'manifest.json').read_text())['files']['src/App.tsx']
    (source/'src/config.ts').write_text(config.replace("clientSecret: ''", "clientSecret: 'do-not-import'"))
    with pytest.raises(ValueError, match='empty defaults'):
        module.restore(source, target)


def test_demo_1016_import_masks_token_and_removes_preset_accounts(tmp_path):
    script = Path(__file__).resolve().parents[3]/'scripts/import_official_web_demo.py'
    spec = importlib.util.spec_from_file_location('import_official_demo_token', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source, target = tmp_path/'source', tmp_path/'restored'
    for relative in ['src/App.tsx', 'src/components/LivePanel.tsx', 'src/components/AIRawFramePanel.tsx', 'src/utils/load-sdk.ts']:
        file = source/relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text('// original source\n')
    config = ("export const DEFAULT_AUTH_CONFIG: AuthConfig = {\n" +
              ''.join(f"  {key}: '',\n" for key in ['appName', 'clientId', 'clientSecret', 'presetKey', 'stationSn', 'eufyUserId', 'accountUuid', 'token']) +
              "};\nconst STORAGE_KEY = 'eufy-web-sdk-demo-auth-config';\nlocalStorage.setItem('secret', 'value');")
    (source/'src/config.ts').write_text(config)
    (source/'src/components/AuthForm.tsx').write_text('<input\n value={form.token} />\n<button disabled={connecting}>preset</button>')
    (source/'src/preset-teams.ts').write_text("export const PRESET_TEAMS = [{token:'synthetic-private-preset'}];")
    (source/'src/services').mkdir()
    (source/'src/services/connect.ts').write_text('onLog(`Token acquired: ${accessToken}`);\n// original login flow')
    manifest = module.restore(source, target)
    assert manifest['supportsDirectToken'] is True
    assert 'synthetic-private-preset' not in (target/'src/preset-teams.ts').read_text(encoding='utf-8')
    assert 'type="password"' in (target/'src/components/AuthForm.tsx').read_text(encoding='utf-8')
    assert '!selectedTeam.token' in (target/'src/components/AuthForm.tsx').read_text(encoding='utf-8')
    assert '${accessToken}' not in (target/'src/services/connect.ts').read_text(encoding='utf-8')
    assert '// original login flow' in (target/'src/services/connect.ts').read_text(encoding='utf-8')
    assert 'localStorage' not in (target/'src/config.ts').read_text(encoding='utf-8')
    (source/'src/config.ts').write_text(config.replace("token: ''", "token: 'synthetic-private-default'"))
    with pytest.raises(ValueError, match='empty defaults: token'):
        module.restore(source, target)
