from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from evidenceguard.app import create_app


def test_web_build_shares_api_without_shadowing_it(tmp_path, monkeypatch):
    web = tmp_path/'web'
    web.mkdir()
    (web/'index.html').write_text('<html>EvidenceGuard Web</html>')
    monkeypatch.setenv('EG_WEB_ROOT', str(web))
    app = create_app(tmp_path/'app.sqlite3', start_worker=False)
    app.state.camera.active.manifests = AsyncMock(return_value=[])
    with TestClient(app) as client:
        assert 'EvidenceGuard Web' in client.get('/').text
        assert client.get('/api/health').json()['status'] == 'ok'
        assert client.get('/api/bootstrap').json()['integration']['physicalDevicesValidated'] is False
        assert client.get('/api/not-a-route').status_code == 404
        assert client.get('/sdk/index.js').status_code == 404
