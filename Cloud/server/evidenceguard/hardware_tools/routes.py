from typing import Literal
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import Field
from ..camera.live import Input
from ..camera.live_routes import limited_json
from ..personal import installation
from .gateway import public
from .vendor.camera_tools.catalog import ToolError


class Route(Input):
    ready: bool
    sdkMapping: str = Field(min_length=1, max_length=240)


class Register(Input):
    deviceId: str = Field(max_length=100)
    model: Literal['T8171','T8214']
    platform: Literal['ios','web','android']
    adapterVersion: str = Field(min_length=1,max_length=100)
    sdkArtifactHash: str = Field(pattern='^[a-f0-9]{64}$')
    firmwareVersion: str = Field(default='unknown',max_length=100)
    privacy: Literal['on','off','unknown'] = 'unknown'
    officialIdentityReady: bool
    routes: dict[str, Route]
    fields: dict = Field(default_factory=dict)
    sessionId: str | None = None
    mediaToken: str | None = None


class Call(Input):
    name: str = Field(max_length=80)
    arguments: dict
    idempotencyKey: str = Field(min_length=1,max_length=128)
    platform: Literal['ios','web','android']
    taskId: str | None = Field(default=None,max_length=256)
    diagnostic: bool = False


class Confirmation(Input):
    operationId: str
    requestHash: str
    decision: Literal['approve','reject']


class Validation(Input):
    deviceId: str
    tool: str
    capabilityRevision: str
    status: Literal['passed','failed','not_run']
    evidence: str = Field(min_length=10,max_length=2000)


class Lease(Input):
    operationId: str = Field(max_length=100)
    leaseToken: str = Field(min_length=1,max_length=128)


class Result(Lease):
    command: Literal['execute','stop'] = 'execute'
    status: Literal['acknowledged','failed','unknown','stopped']
    simulated: Literal[False] = False
    sdkUsed: bool = False
    sdkResult: dict | None = None
    data: dict = Field(default_factory=dict)
    references: list[dict] = Field(default_factory=list,max_length=64)
    error: dict | None = None


class Reconcile(Input):
    operationId: str
    requestHash: str
    decision: Literal['release_after_manual_check']
    evidence: str = Field(min_length=10,max_length=2000)

class PrivacyCheck(Input):
    evidence: str = Field(min_length=10,max_length=2000)


def install_hardware_routes(app, gateway):
    def client(request): return installation(request.headers.get('X-EG-Installation-ID'))
    def executor(request, eid):
        return gateway.executor(client(request),eid,request.headers.get('X-EG-Executor-Token',''))

    @app.exception_handler(ToolError)
    async def tool_error(request, error):
        return JSONResponse(status_code=error.status, content={'detail':error.message,'code':error.code})

    @app.get('/api/hardware/snapshot')
    async def snapshot(request: Request): return gateway.snapshot(client(request))

    @app.post('/api/hardware/call')
    async def call(request: Request):
        return gateway.call(client(request),(await limited_json(request,Call,65536)).model_dump())

    @app.post('/api/hardware/confirmations')
    async def confirm(request: Request):
        body=(await limited_json(request,Confirmation,4096)).model_dump()
        return gateway.sync_run(gateway.runtime.approve(gateway.human(client(request)),body['operationId'],body))

    @app.post('/api/hardware/validations')
    async def validate(request: Request):
        body=(await limited_json(request,Validation,8192)).model_dump()
        return gateway.runtime.validate_hardware(gateway.human(client(request)),body)

    @app.post('/api/hardware/reconcile')
    async def reconcile(request: Request):
        body=(await limited_json(request,Reconcile,8192)).model_dump()
        return gateway.sync_run(gateway.runtime.reconcile(gateway.human(client(request)),body))

    @app.post('/api/hardware/devices/{device_id}/privacy-check')
    async def privacy_check(device_id: str, request: Request):
        body=await limited_json(request,PrivacyCheck,8192)
        return gateway.attest_privacy(client(request),device_id,body.evidence)

    @app.post('/api/hardware/devices/{device_id}/release')
    async def release(device_id: str, request: Request): return gateway.release(client(request),device_id)

    @app.post('/api/hardware/executors')
    async def register(request: Request):
        return gateway.register(client(request),(await limited_json(request,Register,65536)).model_dump())

    @app.post('/api/hardware/executors/{eid}/claim')
    async def claim(eid: str, request: Request): return await gateway.claim(*executor(request,eid))

    @app.post('/api/hardware/executors/{eid}/observe')
    async def observe(eid: str, request: Request):
        p,host=executor(request,eid)
        return await gateway.observe(p,host,(await limited_json(request,Lease,4096)).model_dump())

    @app.post('/api/hardware/executors/{eid}/result')
    async def result(eid: str, request: Request):
        p,_=executor(request,eid)
        return gateway.finish(p,(await limited_json(request,Result,65536)).model_dump(exclude_none=True))

    @app.post('/api/hardware/executors/{eid}/disconnect')
    async def disconnect(eid: str, request: Request): return gateway.disconnect(*executor(request,eid))
