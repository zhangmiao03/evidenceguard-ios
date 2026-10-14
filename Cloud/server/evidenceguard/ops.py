"""Opt-in local observability. Never the source of business state or permissions.

Records go through a bounded, best-effort queue to a separate SQLite database.
No images, credentials, media session tokens, or raw exception messages are stored.
"""
from __future__ import annotations

import asyncio
import contextvars
import functools
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import queue
import re
import sqlite3
import threading
import time
import uuid
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

SCHEMA = 'evidenceguard.ops/v1'
MAX_BYTES = 20_000_000
MAX_RECORDS = 10_000
CTX = contextvars.ContextVar('eg_trace', default={})
RECORDER = contextvars.ContextVar('eg_recorder', default=None)
OPERATION = contextvars.ContextVar('eg_operation', default='model')
SECRET = re.compile(r'authorization|api.?key|secret|password|credential|tokenhash|imagebase64|^token$|^sn$|accountid|clientid|importedby', re.I)
IDENTIFIER = re.compile(r'^[A-Za-z0-9_.:-]{1,120}$')


def identifier(value):
    if isinstance(value,str) and IDENTIFIER.fullmatch(value): return value
    return 'ref-'+hashlib.sha256(str(value).encode()).hexdigest()[:32]


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def safe(value, depth=0):
    if depth > 16: return '[depth omitted]'
    if isinstance(value, dict):
        return {str(k)[:100]: '[redacted]' if SECRET.search(str(k)) else safe(v, depth+1)
                for k, v in list(value.items())[:100]}
    if isinstance(value, (tuple, list)): return [safe(v, depth+1) for v in value[:100]]
    if isinstance(value, str):
        if 'data:' in value and ';base64,' in value: return '[binary omitted]'
        value = re.sub(r'(?i)Bearer\s+\S+', 'Bearer [redacted]', value)
        value = re.sub(r'''(?i)(api[_-]?key|password|secret|access[_-]?token)["']?\s*[=:]\s*["']?[^\s,;"'}]+''', r'\1=[redacted]', value)
        value = re.sub(r'\b(?:sk-[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{30,})\b', '[credential omitted]', value)
        # Never retain signed URLs, usernames/passwords in URLs, or local filesystem paths.
        value = re.sub(r'https?://[^\s"<>]+', '[remote URL omitted]', value)
        return value[:16000]
    if value is None or isinstance(value, (bool, int)): return value
    if isinstance(value, float): return value if math.isfinite(value) else None
    return '[unsupported value]'


def text_ref(value):
    raw = canonical(value)
    return {'omitted': 'dynamic content (capture disabled)', 'characters': len(raw),
            'sha256': hashlib.sha256(raw.encode()).hexdigest()}


def prompt_snapshot(body, capture=False):
    result = safe({k:v for k,v in body.items() if k not in {'messages', 'input'}})
    if 'messages' in body:
        result['messages'] = []
        for i, m in enumerate(body['messages']):
            # Only the first fixed system prompt is visible by default. Memory and
            # contextual system messages can contain private user information.
            content = m.get('content')
            result['messages'].append({'role': m.get('role'),
                'content': safe(content) if capture or (i == 0 and m.get('role') == 'system') else text_ref(content),
                'tool_calls': safe(m.get('tool_calls')) if capture else text_ref(m.get('tool_calls'))})
    if 'input' in body: result['input'] = safe(body['input']) if capture else text_ref(body['input'])
    return {'contentCapture': capture, 'hashMeaning': 'sanitized request snapshot; not wire bytes', 'request': result}


class Recorder:
    def __init__(self, path, *, capacity=2048, retention=20000, capture=False):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.capture = capture
        self.retention = max(100, retention)
        self.dropped = self.write_errors = self.evicted = 0
        self.closed = False
        self.q = queue.Queue(maxsize=capacity)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False, timeout=2)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY, at REAL NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS imports(id TEXT PRIMARY KEY, checksum TEXT NOT NULL, payload TEXT NOT NULL);
        ''')
        self.db.execute('INSERT OR IGNORE INTO metadata VALUES (?,?)', ('datasetId', 'local-'+uuid.uuid4().hex))
        self.dataset_id = self.db.execute('SELECT value FROM metadata WHERE key=?', ('datasetId',)).fetchone()[0]
        self.db.commit()
        self.thread = threading.Thread(target=self._write, name='eg-observability', daemon=True)
        self.thread.start()

    def emit(self, name, *, kind='event', status='observed', data=None, duration=None, trace=None, platform='backend', source='local', record_id=None):
        if self.closed: return
        try:
            ctx = trace if trace is not None else CTX.get()
            record = dict(id=record_id or uuid.uuid4().hex, kind=kind, name=name, at=time.time(),
                traceId=identifier(ctx.get('traceId') or 'unlinked-'+uuid.uuid4().hex),
                spanId=identifier(ctx.get('spanId') or uuid.uuid4().hex), parentSpanId=identifier(ctx['parentSpanId']) if ctx.get('parentSpanId') else None,
                platform=platform, source=source, status=status, durationMs=duration, data=safe(data or {}))
            self.q.put_nowait(record)
        except queue.Full: self.dropped += 1
        except Exception: self.write_errors += 1  # telemetry cannot fail a business request

    def _write(self):
        while True:
            row = self.q.get()
            try:
                if row is None: return
                with self.lock, self.db:
                    self.db.execute('INSERT OR REPLACE INTO records VALUES (?,?,?)', (row['id'], row['at'], canonical(row)))
                    count = self.db.execute('SELECT COUNT(*) FROM records').fetchone()[0]
                    if count > self.retention:
                        n = count - self.retention
                        self.db.execute('DELETE FROM records WHERE id IN (SELECT id FROM records ORDER BY at LIMIT ?)', (n,))
                        self.evicted += n
            except Exception: self.write_errors += 1
            finally: self.q.task_done()

    def flush(self, timeout=3):
        end = time.monotonic()+timeout
        while self.q.unfinished_tasks and time.monotonic()<end: time.sleep(.005)
        return not self.q.unfinished_tasks

    def close(self):
        if self.closed: return
        self.closed = True
        self.flush()
        try: self.q.put(None, timeout=1)
        except queue.Full: return
        self.thread.join(timeout=3)
        if not self.thread.is_alive(): self.db.close()

    def bundle(self):
        with self.lock:
            total = self.db.execute('SELECT COUNT(*) FROM records').fetchone()[0]
            rows = self.db.execute('SELECT payload FROM records ORDER BY at DESC LIMIT ?', (MAX_RECORDS,)).fetchall()
        selected=[]; size=0
        for row in rows:
            size+=len(row[0].encode())
            if size>18_000_000: break
            selected.append(json.loads(row[0]))
        return dict(schemaVersion=SCHEMA,
            dataset=dict(id=self.dataset_id, title='本地追踪', source='local', exportedAt=time.time()),
            records=selected[::-1],
            coverage=dict(totalStored=total, returned=len(selected), truncated=total>len(selected),
                dropped=self.dropped, writeErrors=self.write_errors, evictedSinceStart=self.evicted,
                pending=self.q.unfinished_tasks, contentCapture=self.capture,
                buildRevision=os.getenv('EG_BUILD_REVISION','unknown'),
                clock='server receive wall clock; durations use local monotonic clocks',
                limitations=['No historical backfill', 'No device sensor clock', 'No TTFT (non-streaming providers)',
                             'Usage only when returned by provider; no billing estimate', 'Counter values are since process start']))

    def import_bundle(self, bundle):
        validate_bundle(bundle)
        # Namespace imports separately. They never overwrite current business or
        # local telemetry and are always displayed as unverified imported data.
        cleaned = dict(schemaVersion=SCHEMA,dataset={k:safe(v) for k,v in bundle['dataset'].items() if k in {'id','title','source','exportedAt'}},
            records=[{k:safe(v) if k=='data' else v for k,v in r.items() if k in
                {'id','kind','name','at','traceId','spanId','parentSpanId','platform','source','status','durationMs','data'}} for r in bundle['records']],
            coverage=safe(bundle.get('coverage',{})))
        checksum = digest(cleaned)
        key = bundle['dataset']['id']
        with self.lock, self.db:
            old = self.db.execute('SELECT checksum FROM imports WHERE id=?', (key,)).fetchone()
            if old and old[0] != checksum: raise ValueError('同一数据集 ID 的内容冲突，请生成新的导出 ID')
            if not old:
                self.db.execute('INSERT INTO imports VALUES (?,?,?)', (key, checksum, canonical(cleaned)))
        return {'id':key, 'imported':not bool(old), 'records':len(bundle['records'])}

    def datasets(self):
        with self.lock: rows = self.db.execute('SELECT payload FROM imports ORDER BY id').fetchall()
        return [dict(json.loads(r[0])['dataset'], imported=True) for r in rows]

    def imported(self, key):
        with self.lock: row = self.db.execute('SELECT payload FROM imports WHERE id=?', (key,)).fetchone()
        if not row: raise KeyError(key)
        return json.loads(row[0])


def validate_bundle(value):
    if not isinstance(value, dict) or value.get('schemaVersion') != SCHEMA: raise ValueError('不支持的追踪文件版本')
    if len(canonical(value).encode()) > MAX_BYTES: raise ValueError('文件超过 20 MB')
    ds = value.get('dataset', {})
    if not isinstance(ds, dict) or not isinstance(ds.get('id'),str) or not IDENTIFIER.fullmatch(ds['id']): raise ValueError('数据集 ID 无效')
    if not isinstance(ds.get('title'), str) or len(ds['title'])>200: raise ValueError('数据集标题无效')
    if ds.get('source') not in {'local','synthetic','imported'}: raise ValueError('数据来源无效')
    if not isinstance(ds.get('exportedAt'), (float,int)) or not math.isfinite(ds['exportedAt']): raise ValueError('导出时间无效')
    rows = value.get('records')
    if not isinstance(rows, list) or len(rows)>MAX_RECORDS: raise ValueError('记录必须为数组且不超过 10000 条')
    seen = set()
    for r in rows:
        if not isinstance(r,dict): raise ValueError('记录无效')
        for k in ('id','name','traceId','spanId'):
            if not isinstance(r.get(k), str) or not IDENTIFIER.fullmatch(r[k]): raise ValueError('记录标识无效：'+k)
        if r['id'] in seen: raise ValueError('文件包含重复记录 ID')
        seen.add(r['id'])
        if r.get('parentSpanId') is not None and not IDENTIFIER.fullmatch(str(r['parentSpanId'])): raise ValueError('父 span 无效')
        if r.get('kind') not in {'event','model','prompt','resource'}: raise ValueError('记录类型无效')
        if r.get('platform') not in {'backend','web','ios'}: raise ValueError('平台无效')
        if r.get('source') not in {'local','client','synthetic','snapshot'}: raise ValueError('记录来源无效')
        if not isinstance(r.get('status'),str) or len(r['status'])>80: raise ValueError('状态无效')
        if not isinstance(r.get('at'),(int,float)) or not math.isfinite(r['at']): raise ValueError('记录时间无效')
        d = r.get('durationMs')
        if d is not None and (not isinstance(d,(int,float)) or not math.isfinite(d) or d<0): raise ValueError('耗时无效')
        if not isinstance(r.get('data'),dict): raise ValueError('记录数据无效')
    if not isinstance(value.get('coverage',{}),dict): raise ValueError('覆盖说明无效')
    return value


def traced(name):
    """Scope a business operation without changing return values or exceptions."""
    def decorate(fn):
        @functools.wraps(fn)
        async def wrapped(self, *args, **kwargs):
            recorder = getattr(getattr(self,'store',None),'ops',None) or getattr(self,'ops',None) or RECORDER.get()
            if not recorder: return await fn(self,*args,**kwargs)
            old=CTX.get(); run=args[0] if args and isinstance(args[0],dict) else {}
            ctx=dict(traceId=run.get('id') if name=='agent' else old.get('traceId'),
                     spanId=uuid.uuid4().hex,parentSpanId=old.get('spanId'))
            if not ctx['traceId']: ctx['traceId']=uuid.uuid4().hex
            ctx['traceId']=identifier(ctx['traceId'])
            t=CTX.set(ctx); rt=RECORDER.set(recorder); ot=OPERATION.set(name)
            start=time.monotonic(); status='completed'
            recorder.emit(name+'.started')
            try:
                result=await fn(self,*args,**kwargs)
                if isinstance(result,dict) and isinstance(result.get('status'),str): status=result['status']
                return result
            except asyncio.CancelledError:
                status='cancelled'; raise
            except Exception:
                status='failed'; raise
            finally:
                if name=='agent': status=run.get('status',status)
                recorder.emit(name+'.finished',status=status,duration=round((time.monotonic()-start)*1000,2))
                OPERATION.reset(ot); RECORDER.reset(rt); CTX.reset(t)
        return wrapped
    return decorate


async def model_post(client, url, *, headers, json):
    """One record per real HTTP attempt, separate from output validation outcome."""
    recorder=RECORDER.get()
    if not recorder: return await client.post(url,headers=headers,json=json)
    context=CTX.get(); span=uuid.uuid4().hex
    trace=dict(context,spanId=span,parentSpanId=context.get('spanId'))
    try: snapshot=prompt_snapshot(json,recorder.capture)
    except Exception:
        recorder.write_errors+=1
        return await client.post(url,headers=headers,json=json)
    pid=uuid.uuid4().hex
    recorder.emit('request.snapshot',kind='prompt',record_id=pid,trace=trace,data=snapshot | {'sha256':digest(snapshot)})
    began=time.monotonic(); status='failed'; details=dict(model=json.get('model','unknown'),operation=OPERATION.get(),
        endpointHost=urlsplit(url).hostname,promptId=pid,usage=None,stream=json.get('stream',False),transport='http')
    try:
        response=await client.post(url,headers=headers,json=json)
        details['httpStatus']=response.status_code
        # Headers are allowlisted; never save the whole response or its body.
        details['providerRequestId']=safe(response.headers.get('x-request-id'))
        try:
            body=response.json()
            usage=body.get('usage') if isinstance(body,dict) else None
            details['usage']=safe(usage) if isinstance(usage,dict) else None
        except (ValueError,TypeError): pass
        status='http_ok' if response.status_code<400 else 'http_error'
        return response
    except asyncio.CancelledError:
        status='cancelled'; raise
    except Exception as e:
        details['errorType']=type(e).__name__; raise
    finally:
        recorder.emit(OPERATION.get(),kind='model',status=status,data=details,trace=trace,
                      duration=round((time.monotonic()-began)*1000,2))


CLIENT_NAMES={'api.completed','api.failed','live.first_frame','live.started','live.stopped','live.failed','capture.sampled','agent.displayed','sdk.mode_changed'}
class ClientEvent(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id: str=Field(pattern=r'^[A-Za-z0-9_.:-]{1,120}$')
    name: str=Field(max_length=80)
    traceId: str=Field(pattern=r'^[A-Za-z0-9_.:-]{1,120}$')
    spanId: str=Field(pattern=r'^[A-Za-z0-9_.:-]{1,120}$')
    parentSpanId: str | None=Field(default=None,pattern=r'^[A-Za-z0-9_.:-]{1,120}$')
    platform: str=Field(pattern=r'^(web|ios)$')
    durationMs: float | None=Field(default=None,ge=0,le=86400000,allow_inf_nan=False)
    deviceId: str | None=Field(default=None,max_length=120)
    requestId: str | None=Field(default=None,max_length=120)
    route: str | None=Field(default=None,max_length=200)
    appVersion: str | None=Field(default=None,max_length=80)
    status: str=Field(default='observed',pattern=r'^[A-Za-z0-9_.:-]{1,80}$')


def install_ops(app, store):
    enabled=os.getenv('EG_OPS_ENABLED','0')=='1'
    recorder=None
    if enabled:
        db=Path(store.db.execute('PRAGMA database_list').fetchone()[2])
        path=Path(os.getenv('EG_OPS_DATABASE',str(db.with_name('observability.sqlite3'))))
        if path.resolve()==db.resolve(): raise ValueError('追踪数据库必须与业务数据库分离')
        recorder=Recorder(path,capture=os.getenv('EG_OPS_CAPTURE_CONTENT','0')=='1')
    store.ops=recorder; app.state.ops=recorder

    @app.middleware('http')
    async def trace_request(request,call_next):
        if not recorder or request.url.path.startswith('/api/ops/'):
            response=await call_next(request)
            if request.url.path.startswith('/api/ops/'): response.headers['Cache-Control']='private, no-store'
            return response
        incoming=request.headers.get('X-EG-Trace-ID','')
        trace=incoming if IDENTIFIER.fullmatch(incoming) else uuid.uuid4().hex
        ctx=CTX.set(dict(traceId=trace,spanId=uuid.uuid4().hex,parentSpanId=None))
        rec=RECORDER.set(recorder)
        started=time.monotonic()
        try:
            response=await call_next(request)
            response.headers['X-EG-Trace-ID']=trace
            if request.method!='GET':
                route=request.scope.get('route'); template=getattr(route,'path','unmatched')
                recorder.emit('http.request',status='completed' if response.status_code<400 else 'failed',
                    data={'route':template,'method':request.method,'httpStatus':response.status_code},
                    duration=round((time.monotonic()-started)*1000,2))
            return response
        finally: RECORDER.reset(rec); CTX.reset(ctx)

    def require_ops(request):
        if recorder is None: raise HTTPException(404,'本地追踪未启用')
        expected=os.getenv('EG_OPS_TOKEN','')
        # Team access alone is insufficient for prompt/admin data.
        if expected:
            if len(expected)<32 or not hmac.compare_digest(request.headers.get('X-EG-Ops-Token',''),expected):
                raise HTTPException(403,'需要独立 Dashboard 访问密钥（至少 32 字符）')
        elif os.getenv('EG_ACCESS_TOKEN') or not request.client or request.client.host not in {'127.0.0.1','::1','testclient'} or request.url.hostname not in {'127.0.0.1','localhost','::1','testserver'}:
            raise HTTPException(403,'远程或已启用团队鉴权时，必须配置 EG_OPS_TOKEN')
        # Reject browser cross-origin imports (a localhost service is still sensitive).
        origin=request.headers.get('origin')
        if origin and urlsplit(origin).netloc != request.headers.get('host'):
            raise HTTPException(403,'Dashboard 仅允许同源访问')

    @app.get('/api/ops/snapshot')
    async def snapshot(request:Request):
        require_ops(request)
        return local_bundle()

    def local_bundle():
        bundle=recorder.bundle()
        now=time.time(); resources=[]; counts={}
        fields={'id','name','model','status','state','lifecycle','cameraId','devices','skillId','revision',
                'executionMode','createdAt','updatedAt','capturedAt','sampledAt','receivedAt','observedAt',
                'sourceType','timestampMeaning','duration','segmentCount','expectedOutcome','verdict',
                'platform','registrationSource','ownershipVerified','mediaStatus','taskKind'}
        # Fixed tables/columns only; never arbitrary SQL or imported mutations.
        with store.lock:
            tables={r[0] for r in store.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in ('live_devices','skills','runs','evidence','recordings','skill_trials'):
                if table not in tables: continue
                counts[table]=store.db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                rows=store.db.execute(f'SELECT payload FROM {table} ORDER BY rowid DESC LIMIT 100').fetchall()
                for row in rows:
                    value=json.loads(row[0]); data={k:v for k,v in value.items() if k in fields}
                    resources.append(dict(id='resource:'+table+':'+digest(value.get('id',data))[:24],
                        kind='resource',name=table,at=now,traceId='snapshot:'+table,spanId=uuid.uuid4().hex,
                        parentSpanId=None,source='snapshot',platform='backend',status=str(value.get('status','snapshot')),
                        durationMs=None,data=safe(data)))
        for operation, prefix in (('chat','MODEL'),('image_review','VIDEO'),('embedding','EMBED')):
            model=os.getenv('EG_'+prefix+'_MODEL_ID' if prefix!='MODEL' else 'EG_MODEL_ID','')
            if prefix=='VIDEO': model=model or os.getenv('EG_MODEL_ID','')
            if prefix=='EMBED': model=os.getenv('EG_EMBED_MODEL_ID','')
            resources.append(dict(id='configuration:'+operation,kind='resource',name='model_configuration',at=now,
                traceId='snapshot:configuration',spanId=uuid.uuid4().hex,parentSpanId=None,source='snapshot',platform='backend',
                status='configured' if model else 'not_configured',durationMs=None,data={'operation':operation,'model':model or None}))
        # Leave room for resources without exceeding the portable bundle limit.
        room=MAX_RECORDS-len(resources)
        if len(bundle['records'])>room: bundle['coverage']['truncated']=True
        bundle['records']=bundle['records'][-room:]+resources
        bundle['coverage'].update(returned=len(bundle['records']),resourceCounts=counts,
            resourceLimitPerTable=100,resourceSnapshotsAt=now,resourcesTruncated=any(v>100 for v in counts.values()))
        return bundle

    @app.get('/api/ops/datasets')
    async def datasets(request:Request):
        require_ops(request)
        return recorder.datasets()

    @app.get('/api/ops/export')
    async def export(request:Request,dataset:str | None=None):
        require_ops(request)
        bundle=recorder.imported(dataset) if dataset else local_bundle()
        if not dataset:
            # Each export is an immutable snapshot; import IDs cannot drift.
            bundle['dataset']['id']+='-'+uuid.uuid4().hex[:12]
        return bundle

    @app.post('/api/ops/import')
    async def import_data(request:Request):
        require_ops(request)
        raw=bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw)>MAX_BYTES: raise HTTPException(413,'文件超过 20 MB')
        try: value=json.loads(raw)
        except (ValueError,UnicodeError,RecursionError): raise HTTPException(422,'不是有效 JSON')
        try: return recorder.import_bundle(value)
        except (ValueError,RecursionError,TypeError) as e: raise HTTPException(422,str(e)[:160])

    @app.post('/api/ops/client-events')
    async def client_events(request:Request):
        if recorder is None: return {'accepted':0,'enabled':False}
        raw=bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw)>32768: raise HTTPException(413,'埋点批次过大')
        try:
            values=json.loads(raw)
            if not isinstance(values,list) or len(values)>32: raise ValueError()
            items=[ClientEvent.model_validate(v) for v in values]
            if any(x.name not in CLIENT_NAMES for x in items): raise ValueError()
        except (ValueError,TypeError,RecursionError): raise HTTPException(422,'埋点格式无效')
        installation=request.headers.get('X-EG-Installation-ID','')
        if not IDENTIFIER.fullmatch(installation): raise HTTPException(422,'缺少客户端安装标识')
        for item in items:
            data=item.model_dump(exclude_none=True)
            # Server-scoped IDs prevent one installation overwriting another.
            rid='client-'+hashlib.sha256((installation+':'+item.id).encode()).hexdigest()
            recorder.emit(item.name,record_id=rid,source='client',platform=item.platform,status=item.status,
                duration=item.durationMs,trace=dict(traceId=item.traceId,spanId=item.spanId,parentSpanId=item.parentSpanId),
                data={k:v for k,v in data.items() if k in {'deviceId','requestId','route','appVersion'}})
        return {'accepted':len(items),'enabled':True}

    return recorder
