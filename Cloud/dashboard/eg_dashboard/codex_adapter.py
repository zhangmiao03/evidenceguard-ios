"""Observe the deployed Codex stdio boundary without changing its tool loop.

A complete() call is one host/executor step, not a provider HTTP attempt.
Codex owns the wire request, built-in instructions and usage accounting. Only
host-visible inputs, protocol messages and returned outputs are recorded here.
"""
import asyncio
import functools
import importlib
import time
import uuid

from . import content


def install(ops, cls=None):
    if cls is None:
        try:
            cls = importlib.import_module('evidenceguard.harness.codex').CodexTurn
        except ModuleNotFoundError as error:
            if error.name != 'evidenceguard.harness.codex':
                raise
            return
    if getattr(cls, '_dashboard_instrumented', False):
        return

    def observe(callback):
        # Neither a full queue nor a malformed observation changes execution.
        try:
            recorder = ops.RECORDER.get()
            if recorder:
                callback(recorder)
        except Exception:
            pass

    original_complete = cls.complete
    @functools.wraps(original_complete)
    async def complete(self, messages, tools):
        if not ops.RECORDER.get():
            return await original_complete(self, messages, tools)
        old = ops.CTX.get()
        trace = dict(old, spanId=uuid.uuid4().hex, parentSpanId=old.get('spanId'))
        token = ops.CTX.set(trace)
        pid = uuid.uuid4().hex
        data = dict(model=self.provider.model, operation='codex_step',
                    transport='codex_app_server', promptId=pid, wireHttpVisible=False,
                    inputBoundary='host_to_codex', usage=None)
        started = time.monotonic()
        status = 'failed'
        def inputs(recorder):
            request = dict(model=self.provider.model, messages=messages, tools=tools,
                           continuation=bool(self.thread_id))
            if content.enabled():
                snapshot, capture = content.clean(request)
                body = dict(request=snapshot, capture=capture, sha256=ops.digest(snapshot),
                            contentCapture=True, hashMeaning='secret-filtered host input; not provider wire bytes')
            else:
                body = ops.prompt_snapshot(request, False)
            recorder.emit('request.snapshot', kind='prompt', record_id=pid,
                          data=dict(body, transport='codex_app_server', inputBoundary='host_to_codex'))
            recorder.emit('context.prepared', data=dict(transport='codex_app_server',
                          **content.details(messages=messages, tools=tools)))
        try:
            observe(inputs)
            result = await original_complete(self, messages, tools)
            status = 'executor_ok'
            data.update(content.details(response=result))
            observe(lambda r: r.emit('model.output', data=dict(transport='codex_app_server',
                                    **content.details(output=result))))
            return result
        except asyncio.CancelledError:
            status = 'cancelled'
            raise
        except Exception as error:
            data['errorType'] = type(error).__name__
            data.update(content.details(error=str(error)))
            raise
        finally:
            try:
                data.update(threadId=self.thread_id, turnId=self.turn_id)
                observe(lambda r: r.emit('codex_step', kind='model', status=status, data=data,
                            duration=round((time.monotonic() - started) * 1000, 2)))
            finally:
                ops.CTX.reset(token)

    original_send = cls.send
    @functools.wraps(original_send)
    async def send(self, value):
        result = await original_send(self, value)
        def sent(recorder):
            method = value.get('method')
            if method in {'thread/start', 'thread/inject_items', 'turn/start'}:
                label = method
            elif not method and 'id' in value and ('result' in value or 'error' in value):
                label = 'item/tool/call:response'
            else:
                return
            recorder.emit('codex.request', data=dict(transport='codex_app_server',
                          method=label, requestId=value.get('id'), **content.details(message=value)))
        observe(sent)
        return result

    original_read = cls.read
    @functools.wraps(original_read)
    async def read(self):
        value = await original_read(self)
        def received(recorder):
            method = value.get('method')
            params = value.get('params', {})
            message = value
            if method == 'item/completed':
                if params.get('item', {}).get('type') != 'agentMessage':
                    return  # Never record private reasoning items or deltas.
            elif method == 'turn/completed':
                # Turn.items may include hidden reasoning; retain lifecycle data
                # only. Actual agent text is captured separately above.
                turn = params.get('turn', {})
                message = dict(value, params=dict(params, turn={
                    k: turn[k] for k in ('id', 'status', 'error') if k in turn}))
            elif method not in {'item/tool/call', 'thread/tokenUsage/updated', 'error'}:
                return
            recorder.emit('codex.usage' if method == 'thread/tokenUsage/updated' else 'codex.response',
                          data=dict(transport='codex_app_server', method=method,
                                    usageMeaning='executor snapshot; not summed across steps' if method == 'thread/tokenUsage/updated' else None,
                                    **content.details(message=message)))
        observe(received)
        return value

    cls.complete, cls.send, cls.read = complete, send, read
    cls._dashboard_instrumented = True
