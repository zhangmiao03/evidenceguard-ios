"""Optional client-reported display hashes. No reply body or secrets accepted."""
import hashlib
import json
import re
from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field


class DisplayReceipt(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(pattern=r'^[A-Za-z0-9_.:-]{1,120}$')
    runId: str = Field(pattern=r'^[A-Za-z0-9_.:-]{1,120}$')
    backendTextHash: str = Field(pattern=r'^[a-f0-9]{64}$')
    displayTextHash: str = Field(pattern=r'^[a-f0-9]{64}$')
    presentationVersion: str = Field(pattern=r'^[A-Za-z0-9_.:-]{1,80}$')
    appVersion: str = Field(max_length=80)
    platform: str = Field(pattern=r'^(ios|web)$')
    status: str = Field(pattern=r'^[A-Za-z0-9_.:-]{1,80}$')


def install(app, store):
    path = '/api/ops/display-receipts'
    if any(getattr(r, 'path', '') == path for r in app.routes): return

    @app.post(path)
    async def receive(request: Request):
        recorder = getattr(store, 'ops', None)
        if recorder is None: return {'accepted':0,'enabled':False}
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 4096: raise HTTPException(413, 'Display receipt too large')
        try: item = DisplayReceipt.model_validate(json.loads(raw))
        except (ValueError, TypeError, RecursionError): raise HTTPException(422, 'Invalid display receipt')
        installation = request.headers.get('X-EG-Installation-ID', '')
        if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,120}', installation): raise HTTPException(422, 'Missing installation identity')
        rid = 'display-' + hashlib.sha256((installation+':'+item.id).encode()).hexdigest()
        recorder.emit('agent.displayed', record_id=rid, source='client', platform=item.platform, status=item.status,
            trace={'traceId':item.runId,'spanId':item.id,'parentSpanId':None},
            data={**item.model_dump(exclude={'id','runId','status','platform'}), 'clientReported':True,'hashAlgorithm':'sha256_utf8'})
        return {'accepted':1,'enabled':True}
