"""SDK relay HTTP contracts shared by iOS and Web; all use team authorization."""
from __future__ import annotations

import httpx
import json
from fastapi import HTTPException, Request, Response

from ..personal import installation
from .live import DeviceImport, SessionStart, Heartbeat, FrameUpload, CaptureRequest


async def limited_json(request, model, limit=8_000_000):
    data = bytearray()
    async for part in request.stream():
        data.extend(part)
        if len(data) > limit:
            raise HTTPException(413, '请求内容过大')
    from pydantic import ValidationError
    try:
        return model.model_validate_json(bytes(data))
    except ValidationError:
        # Never echo base64 frames, Wi-Fi secrets or vendor credentials.
        raise HTTPException(422, '请求字段、格式或范围不正确')


def install_live_routes(app, camera, captures):
    from .official_demo import install_official_demo_routes
    install_official_demo_routes(app)
    hub = camera.live

    def session(sid, request):
        return hub.authorize(sid, installation(request.headers.get('X-EG-Installation-ID')),
                             request.headers.get('X-EG-Media-Session', ''))

    @app.get('/api/devices')
    async def devices():
        manifests = {m.id: m.api_dict() for m in await hub.manifests()}
        return [d | manifests[d['id']] for d in hub.records()]

    @app.get('/api/captures')
    async def recent_captures():
        # Completed camera receipts persist independently of volatile sessions.
        with hub.store.lock:
            rows = hub.store.db.execute("SELECT payload FROM events WHERE type='camera_completed' ORDER BY id DESC LIMIT 100").fetchall()
        names = {d['id']: d['name'] for d in hub.records()}
        return [value | {'deviceName': names.get(value['cameraId'], value['cameraId'])}
                for row in rows if (value := json.loads(row[0])).get('status') == 'completed'
                and value.get('imageUrl') and value.get('sourceType', '').startswith('official_live_')]

    @app.post('/api/devices/import')
    async def import_devices(body: DeviceImport, request: Request):
        """登记客户端报告的已绑定设备，按 SN 去重；不执行官方配网、绑定或所有权核验。"""
        return hub.import_devices(body, installation(request.headers.get('X-EG-Installation-ID')))

    @app.post('/api/media-sessions', status_code=201)
    async def start(body: SessionStart, request: Request):
        return hub.start(body, installation(request.headers.get('X-EG-Installation-ID')))

    @app.post('/api/media-sessions/{sid}/heartbeat')
    async def heartbeat(sid: str, body: Heartbeat, request: Request):
        return hub.heartbeat(session(sid, request), body)

    @app.get('/api/media-sessions/{sid}/commands')
    async def commands(sid: str, request: Request):
        return hub.commands(session(sid, request))

    @app.post('/api/media-sessions/{sid}/frames')
    async def frame(sid: str, request: Request):
        """回传本会话领取请求后的新帧；sampledAt 为客户端取样时间，channelId 当前仅 main。

        需 X-EG-Installation-ID 与 X-EG-Media-Session。不能以历史事件缩略图回应新画面请求。
        """
        s = session(sid, request)
        body = await limited_json(request, FrameUpload)
        return hub.upload(s, body)

    @app.post('/api/media-sessions/{sid}/stop')
    async def stop(sid: str, request: Request):
        hub.stop(session(sid, request))
        return {'status': 'stopped'}

    @app.post('/api/devices/{device_id}/capture')
    async def capture(device_id: str, body: CaptureRequest):
        hub.record(device_id)
        owner = captures.store.owner(device_id)
        return await captures.capture(device_id, owner['id'] if owner else None, body.purpose)

    # The official browser SDK needs OpenAPI CORS support. Only this fixed
    # vendor host is reachable; this is not a user-selectable URL proxy.
    @app.get('/api/sdk/openapi/{path:path}')
    @app.post('/api/sdk/openapi/{path:path}')
    async def vendor_proxy(path: str, request: Request):
        if (not path.startswith('v1/') or any(x in path for x in ('..', '//', '\\', ':', '%'))
                or len(path) > 240):
            raise HTTPException(400, '无效的官方 API 路径')
        body = bytearray()
        async for part in request.stream():
            body.extend(part)
            if len(body) > 2_000_000:
                raise HTTPException(413, '官方 API 请求过大')
        blocked = {'host', 'cookie', 'content-length', 'connection', 'origin', 'referer', 'accept-encoding'}
        headers = {k: v for k, v in request.headers.items()
                   if k not in blocked and not k.startswith(('x-eg-', 'sec-', 'forwarded', 'x-forwarded'))}
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
                upstream = await client.request(request.method, 'https://openapi-us.eufylife.com/' + path,
                                                params=request.query_params, content=bytes(body), headers=headers)
        except httpx.HTTPError:
            raise HTTPException(502, '官方服务暂不可达，请检查网络后重试')
        return Response(upstream.content, status_code=upstream.status_code,
                        headers={'Content-Type': upstream.headers.get('content-type', 'application/json'),
                                 'Cache-Control': 'no-store'})
