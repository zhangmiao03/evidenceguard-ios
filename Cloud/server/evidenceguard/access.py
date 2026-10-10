"""Single-team beta access. Media cookies grant only GET/HEAD of media routes."""
import hashlib
import hmac
import os
import re
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

COOKIE = 'eg_media'
MEDIA = re.compile(r'^/api/(?:media/[a-f0-9]{64}|recordings/[^/]+/(?:video|preview)|replay-evidence/[^/]+/video|skill-trials/[^/]+/video|camera/frames/[^/]+/[^/]+)$')


class TeamAccess(BaseHTTPMiddleware):
    def __init__(self, app, token: str):
        super().__init__(app)
        if len(token) < 32 or not token.isascii() or any(c.isspace() for c in token):
            raise ValueError('EG_ACCESS_TOKEN must be an ASCII token of at least 32 characters')
        self.token = token

    def cookie(self, expires: int) -> str:
        value = f'media:{expires}'.encode()
        signature = hmac.new(self.token.encode(), value, hashlib.sha256).hexdigest()
        return f'{expires}.{signature}'

    def valid_cookie(self, value: str) -> bool:
        try:
            expires, _ = value.split('.', 1)
            expiry = int(expires)
            return time.time() < expiry <= time.time() + 21600 and hmac.compare_digest(value, self.cookie(expiry))
        except (ValueError, TypeError):
            return False

    async def dispatch(self, request, call_next):
        if request.url.path == '/api/health' and request.method in {'GET', 'HEAD'}:
            return JSONResponse({'status': 'ok'})
        bearer = request.headers.get('authorization', '')
        authorized = hmac.compare_digest(bearer.encode(), ('Bearer ' + self.token).encode())
        media_cookie = (request.method in {'GET', 'HEAD'} and MEDIA.fullmatch(request.url.path)
                        and self.valid_cookie(request.cookies.get(COOKIE, '')))
        if not authorized and not media_cookie:
            return JSONResponse({'detail': '请输入有效的团队访问令牌'}, status_code=401,
                                headers={'WWW-Authenticate': 'Bearer', 'Cache-Control': 'no-store'})
        response = await call_next(request)
        response.headers['Cache-Control'] = 'private, no-store'
        if authorized:
            response.set_cookie(COOKIE, self.cookie(int(time.time()) + 21590), max_age=21590,
                                secure=True, httponly=True, samesite='strict', path='/api')
        return response


def install_access(app):
    required = os.getenv('EG_REQUIRE_AUTH', '0') == '1'
    token = os.getenv('EG_ACCESS_TOKEN', '')
    if required and len(token) < 32:
        raise RuntimeError('Public deployment requires EG_ACCESS_TOKEN (at least 32 characters)')
    if token:
        app.add_middleware(TeamAccess, token=token)
