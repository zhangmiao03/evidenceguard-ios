import time

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from fastapi.responses import FileResponse

from evidenceguard.access import COOKIE, TeamAccess, install_access

TOKEN = 'beta-test-' + 'a' * 48


@pytest.fixture
def protected(tmp_path):
    app = FastAPI()
    app.add_middleware(TeamAccess, token=TOKEN)
    media = tmp_path / 'video.mp4'
    media.write_bytes(b'0123456789')

    @app.get('/api/bootstrap')
    def bootstrap():
        return {'team': 'demo'}

    @app.api_route('/api/recordings/test/video', methods=['GET', 'HEAD'])
    def video():
        return FileResponse(media, media_type='video/mp4')

    @app.post('/api/recordings')
    async def upload(request: Request):
        return {'size': len(await request.body())}

    return TestClient(app, base_url='https://testserver')


def test_unauthorized_api_and_media_blocked(protected):
    assert protected.get('/api/bootstrap').status_code == 401
    assert protected.get('/api/recordings/test/video').status_code == 401
    assert protected.get('/docs').status_code == 401
    assert protected.get('/api/bootstrap', headers={'Authorization': 'Bearer wrong'}).status_code == 401
    assert protected.get('/api/health').json() == {'status': 'ok'}


def test_bearer_sets_secure_cookie_without_granting_api_access(protected):
    response = protected.get('/api/bootstrap', headers={'Authorization': f'Bearer {TOKEN}'})
    assert response.status_code == 200
    cookie = response.headers['set-cookie']
    assert all(flag in cookie for flag in ['HttpOnly', 'Secure', 'SameSite=strict', 'Path=/api'])
    assert TOKEN not in cookie
    assert protected.get('/api/bootstrap').status_code == 401
    assert protected.post('/api/recordings', content=b'test').status_code == 401
    assert protected.get('/api/recordings/test/video', headers={'Range': 'bytes=2-5'}).content == b'2345'
    assert protected.head('/api/recordings/test/video').status_code == 200


def test_tampered_and_expired_cookie_rejected(protected):
    signer = TeamAccess(FastAPI(), token=TOKEN)
    expired = signer.cookie(int(time.time()) - 1)
    for value in [expired, signer.cookie(int(time.time()) + 30) + '0', 'invalid']:
        assert protected.get('/api/recordings/test/video', headers={'Cookie': f'{COOKIE}={value}'}).status_code == 401


def test_cookie_not_transmitted_over_http(protected):
    protected.get('/api/bootstrap', headers={'Authorization': f'Bearer {TOKEN}'})
    assert protected.get('http://testserver/api/recordings/test/video').status_code == 401


def test_authenticated_upload_body_preserved(protected):
    body = b'frame' * 10000
    response = protected.post('/api/recordings', content=body, headers={'Authorization': f'Bearer {TOKEN}'})
    assert response.json() == {'size': len(body)}


def test_public_mode_requires_token(monkeypatch):
    monkeypatch.setenv('EG_REQUIRE_AUTH', '1')
    monkeypatch.delenv('EG_ACCESS_TOKEN', raising=False)
    with pytest.raises(RuntimeError, match='EG_ACCESS_TOKEN'):
        install_access(FastAPI())
