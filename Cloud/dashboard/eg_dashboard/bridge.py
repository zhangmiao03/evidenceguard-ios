"""Add observations without replacing deployed business logic or credentials.

The existing ops module is the single recorder implementation. The release
builder copies it as _ops_runtime.py for older deployments that lack it.
"""
from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
import functools
import hashlib
import importlib
import inspect
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace
import uuid
from . import content, transport, codex_adapter


def load_ops():
    try:
        return importlib.import_module('evidenceguard.ops'), True
    except ModuleNotFoundError as error:
        if error.name != 'evidenceguard.ops':
            raise
        return importlib.import_module('eg_dashboard._ops_runtime'), False


def summary(value):
    """Public metadata, not conversation contents or model reasoning."""
    try:
        encoded = json.dumps(value, ensure_ascii=False, default=str)
        result = {'type': type(value).__name__, 'characters': len(encoded),
                  'sha256': hashlib.sha256(encoded.encode()).hexdigest()}
        if isinstance(value, dict):
            result['keys'] = [str(k)[:80] for k in list(value)[:40]]
            for key in ('status', 'verdict', 'executionState', 'sourceType', 'timestampMeaning'):
                if isinstance(value.get(key), str) and len(value[key]) < 80:
                    result[key] = value[key]
            result['hasError'] = bool(value.get('error'))
        if isinstance(value, (list, tuple)):
            result['count'] = len(value)
        return result
    except Exception:
        return {'type': 'unavailable'}


def instrument(ops, native):
    try:
        from .trace_retention import install as install_retention
    except ImportError:
        from evidenceguard.trace_retention import install as install_retention
    install_retention(ops)
    runtime = importlib.import_module('evidenceguard.harness.runtime')
    providers = importlib.import_module('evidenceguard.harness.providers')
    tools = importlib.import_module('evidenceguard.harness.tools')
    store_module = importlib.import_module('evidenceguard.store')
    if getattr(runtime.AgentRuntime, '_dashboard_instrumented', False):
        return
    transport.install(ops)
    codex_adapter.install(ops)

    original_execute = runtime.AgentRuntime._execute
    @functools.wraps(original_execute)
    async def execute(self, run, *args, **kwargs):
        try:
            return await original_execute(self, run, *args, **kwargs)
        finally:
            recorder = getattr(self.store, 'ops', None)
            if recorder:
                recorder.emit('agent.result', status=run.get('status', 'unknown'),
                    trace={'traceId':run['id']} if native else None,
                    data={'executionMode': run.get('executionMode'),
                          'answer': summary(run.get('text')), 'toolReceipts': summary(run.get('toolReceipts', [])),
                          'errorPresent': bool(run.get('error')),
                          **({} if run.get('referenceImageId') or run.get('privateContent') or run.get('endpointAnalyses') else content.details(answer=run.get('text'), toolReceipts=run.get('toolReceipts', []), error=run.get('error')))})
    runtime.AgentRuntime._execute = execute if native else ops.traced('agent')(execute)

    original_tool = tools.ToolRegistry.call
    @functools.wraps(original_tool)
    async def tool_call(self, *args, **kwargs):
        name = args[0] if args else kwargs.get('tool_name', 'unknown')
        recorder = ops.RECORDER.get()
        if not recorder:
            return await original_tool(self, *args, **kwargs)
        old = ops.CTX.get()
        ctx = dict(traceId=old.get('traceId'), spanId=uuid.uuid4().hex, parentSpanId=old.get('spanId'))
        token = ops.CTX.set(ctx)
        start = time.monotonic()
        status = 'failed'
        result_info = {}
        private_search=name in {'search_recordings','analyze_visual_endpoints','sample_camera_vision','aim_camera_at_guard_target','read_visual_control'}
        captured = {} if private_search else content.details(arguments=kwargs, positionalArguments=args[1:])
        recorder.emit('tool.started', data={'tool': name, 'arguments': summary(kwargs), **captured})
        try:
            result = await original_tool(self, *args, **kwargs)
            result_info = summary(result)
            captured = {} if private_search else content.details(arguments=kwargs, positionalArguments=args[1:], result=result)
            status = 'failed' if isinstance(result, dict) and (result.get('error') or result.get('status') in {'failed', 'error', 'unsupported'}) else 'completed'
            return result
        except asyncio.CancelledError:
            status = 'cancelled'
            raise
        except Exception as error:
            captured = {} if private_search else content.details(arguments=kwargs, positionalArguments=args[1:], error=str(error))
            raise
        finally:
            recorder.emit('tool.finished', status=status,
                duration=round((time.monotonic()-start)*1000, 2),
                data={'tool': name, 'result': result_info, **captured})
            ops.CTX.reset(token)
    tools.ToolRegistry.call = tool_call

    original_complete = providers.OpenAICompatibleProvider.complete
    @functools.wraps(original_complete)
    async def complete(self, messages, tools):
        recorder = ops.RECORDER.get() or getattr(self, 'ops', None)
        if recorder:
            recorder.emit('context.prepared', data={
                'messages': [{'role': m.get('role'), 'content': summary(m.get('content'))} for m in messages],
                'tools': [s.get('function', {}).get('name') for s in tools],
                **content.details(messages=messages, tools=tools)})
        result = await original_complete(self, messages, tools)
        if recorder:
            recorder.emit('model.output', data={'answer': summary(result.get('content')),
                'toolCalls': [{'name': c.get('function', {}).get('name'),
                               'arguments': summary(c.get('function', {}).get('arguments'))}
                              for c in result.get('tool_calls', []) or []],
                **content.details(output=result)})
        return result
    providers.OpenAICompatibleProvider.complete = complete if native else ops.traced('chat')(complete)

    if not native:
        original_event = store_module.Store.event
        @functools.wraps(original_event)
        def event(self, run_id, event_type, payload):
            value = original_event(self, run_id, event_type, payload)
            recorder = getattr(self, 'ops', None)
            if recorder:
                fields = {'step','name','tool','status','cameraId','deviceId','requestId','sourceType',
                          'sampledAt','receivedAt','timestampMeaning','mediaId','inputKind','code','reasonCode',
                          'executor','version','threadId','turnId','inputTokens','cachedInputTokens',
                          'outputTokens','reasoningOutputTokens','totalTokens'}
                data = {k:v for k,v in payload.items() if k in fields} if isinstance(payload,dict) else {}
                data.update(legacySubjectId=run_id, sequence=value.get('sequence'))
                recorder.emit(event_type, status=data.get('status') or ('failed' if event_type.endswith('failed') else 'observed'),
                    data=data, trace=ops.CTX.get() or {'traceId':'subject:'+str(run_id)})
            return value
        store_module.Store.event = event

        video = importlib.import_module('evidenceguard.video.providers')
        for class_name, methods in {'LiteVideoProvider': {'verify':'video_verify', 'observe_frame':'frame_presence',
                'describe_observation':'image_review','describe_observations':'image_review'},
                'ArkVideoEmbedding':{'embed':'embedding'}}.items():
            cls = getattr(video, class_name, None)
            for method, label in methods.items():
                if cls and inspect.iscoroutinefunction(getattr(cls, method, None)):
                    setattr(cls, method, ops.traced(label)(getattr(cls, method)))
        try:
            camera = importlib.import_module('evidenceguard.camera.service')
            camera.CameraService.capture = ops.traced('camera.capture')(camera.CameraService.capture)
        except (ImportError, AttributeError):
            pass

        import httpx
        original_post = httpx.AsyncClient.post
        @functools.wraps(original_post)
        async def post(self, url, *args, **kwargs):
            # Scope interception to model requests inside an observed operation.
            body = kwargs.get('json')
            model_operation = ops.OPERATION.get() in {'chat','video_verify','frame_presence','image_review','embedding'}
            if model_operation and ops.RECORDER.get() and isinstance(body,dict) and body.get('model') and not args and set(kwargs) <= {'json','headers'}:
                adapter = SimpleNamespace(post=functools.partial(original_post, self))
                return await ops.model_post(adapter, url, headers=kwargs.get('headers', {}), json=body)
            return await original_post(self, url, *args, **kwargs)
        httpx.AsyncClient.post = post

    runtime.AgentRuntime._dashboard_instrumented = True


def source_files(root):
    root = Path(root)
    return {str(p.relative_to(root)).replace('\\','/'): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*.py')) if '__pycache__' not in p.parts and p.is_file() and not p.is_symlink()}


def attach(app, ops, native):
    store = app.state.store
    if not native:
        ops.install_ops(app, store)
    recorder = getattr(store, 'ops', None)
    if not recorder:
        raise RuntimeError('Observer enabled without recorder')
    try:
        from .display_receipts import install as install_receipts
    except ImportError:
        from evidenceguard.display_receipts import install as install_receipts
    install_receipts(app, store)
    for name in ('evidenceguard.harness.providers', 'evidenceguard.video.providers'):
        module = importlib.import_module(name)
        for item in vars(module).values():
            if isinstance(item, type) and item.__module__ == name:
                item.ops = recorder
    runtime = importlib.import_module('evidenceguard.harness.runtime')
    source = Path(runtime.__file__).resolve().parents[1]
    video_service = getattr(app.state, 'videos', None)
    if video_service and content.enabled():
        from .retrieval import observe_search
        observe_search(video_service, ops, recorder)
    configured_models = {
        'chat': getattr(app.state.agent.model_provider, 'model', None) or os.getenv('EG_MODEL_ID') or None,
        'image': getattr(getattr(video_service, 'vision', None), 'model', None) or os.getenv('EG_VIDEO_MODEL_ID') or os.getenv('EG_MODEL_ID') or None,
        'embedding': getattr(getattr(video_service, 'embedding', None), 'model', None) or os.getenv('EG_EMBED_MODEL_ID') or None,
    }
    endpoint_vision = getattr(app.state,'endpoint_vision',None)
    if endpoint_vision:
        configured_models['endpoint_vision'] = endpoint_vision.configuration().get('model')
    prompt_catalog = [ops.safe(endpoint_vision.prompt_catalog())] if endpoint_vision else []
    if getattr(app.state,'visual_control',None):
        from evidenceguard.vision.control import GROUNDING_PROMPT, GROUNDING_HASH
        prompt_catalog.append(dict(operation='vision.ground_target',version='visual-step-v1',sha256=GROUNDING_HASH,
                                   systemPrompt=GROUNDING_PROMPT,status='loaded_read_only_grounding'))
    state = {'startedAt': time.time(), 'pid': os.getpid(), 'appVersion': app.version,
             'environment': os.getenv('EG_DASHBOARD_ENVIRONMENT','local'),
             'observerRevision': os.getenv('EG_DASHBOARD_REVISION','development'),
             'nativeOps': native, 'files': source_files(source),
             'contentCapture': content.enabled(),
             'executor': getattr(app.state.agent, 'executor', 'bounded-chat-v1'),
             'models': configured_models,
             'embeddingSignature': getattr(video_service, 'index_signature', getattr(getattr(video_service, 'embedding', None), 'signature', None)),
             'videoRoot': str(getattr(video_service, 'root', '')),
             'systemPrompt': ops.safe(getattr(runtime,'SYSTEM','')),
             'promptCatalog': prompt_catalog,
             'tools': ops.safe(app.state.tools.schemas)}
    target = Path(recorder.path).with_name('observer-state.json')
    target.write_text(json.dumps(state, ensure_ascii=False),encoding='utf-8')
    recorder.emit('observer.started',data={'nativeOps':native,'environment':state['environment'],
        'observerRevision':state['observerRevision'],'appVersion':app.version})
    lifespan = app.router.lifespan_context
    @asynccontextmanager
    async def observed_lifespan(application):
        try:
            async with lifespan(application):
                yield
        finally:
            await asyncio.to_thread(recorder.close)
    app.router.lifespan_context = observed_lifespan
    return app

