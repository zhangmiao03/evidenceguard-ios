"""Opt-in body capture around the existing model HTTP call, without retries.

The caller receives the same response/exception. No authorization headers are
captured. Native and legacy backends share this one observer implementation.
"""
import asyncio
import functools
import sys
import time
import uuid
from urllib.parse import urlsplit

from . import content


def install(ops):
    if not content.enabled() or getattr(ops, '_dashboard_content_installed', False):
        return
    original = ops.model_post
    ops.safe = content.safe_record
    original_recorder_init = ops.Recorder.__init__
    @functools.wraps(original_recorder_init)
    def recorder_init(self, *args, **kwargs):
        # Full body entries are larger. A bounded best-effort queue keeps a slow
        # disk from retaining gigabytes or blocking camera/model requests.
        kwargs['capacity'] = min(kwargs.get('capacity', 64), 64)
        original_recorder_init(self, *args, **kwargs)
    ops.Recorder.__init__ = recorder_init

    @functools.wraps(original)
    async def model_post(client, url, *, headers, json):
        privacy=getattr(ops,'PRIVATE_CONTENT',None)
        if privacy is not None and privacy.get():
            # The business service's private-content boundary overrides public
            # dashboard capture, including media_assets.capture_inputs.
            return await original(client,url,headers=headers,json=json)
        recorder = ops.RECORDER.get()
        if not recorder:
            return await client.post(url, headers=headers, json=json)
        ctx = ops.CTX.get()
        trace = dict(ctx, spanId=uuid.uuid4().hex, parentSpanId=ctx.get('spanId'))
        pid = uuid.uuid4().hex
        try:
            from .media_assets import capture_inputs
            inputs = await asyncio.to_thread(capture_inputs, json, recorder)
            request, capture = content.clean(json)
            snapshot = {'request': request, 'capture': capture, 'contentCapture': True,
                        'inputMedia': inputs,
                        'hashMeaning': 'secret-filtered request snapshot; not wire bytes'}
            snapshot['sha256'] = ops.digest(request)
            recorder.emit('request.snapshot', kind='prompt', record_id=pid, trace=trace, data=snapshot)
        except Exception:
            recorder.write_errors += 1
            # Observation failure never retries or suppresses a model call.
        began = time.monotonic()
        status = 'failed'
        data = dict(model=json.get('model', 'unknown'), operation=ops.OPERATION.get(),
                    endpointHost=urlsplit(str(url)).hostname, promptId=pid, usage=None,
                    stream=json.get('stream', False), transport='http')
        try:
            response = await client.post(url, headers=headers, json=json)
            status = 'http_ok' if response.status_code < 400 else 'http_error'
            try:
                data['httpStatus'] = response.status_code
                data['providerRequestId'] = response.headers.get('x-request-id')
                try:
                    body = response.json()
                except (ValueError, TypeError):
                    body = response.text
                if isinstance(body, dict) and isinstance(body.get('usage'), dict):
                    data['usage'] = body['usage']
                data.update(content.details(response=body))
            except Exception:
                data['capture'] = {'version': 1, 'mode': 'unavailable', 'truncated': False}
            return response
        except asyncio.CancelledError:
            status = 'cancelled'
            raise
        except Exception as error:
            data['errorType'] = type(error).__name__
            data.update(content.details(error=str(error)))
            raise
        finally:
            recorder.emit(ops.OPERATION.get(), kind='model', status=status, data=data,
                          trace=trace, duration=round((time.monotonic() - began) * 1000, 2))

    ops.model_post = model_post
    # Several native providers import the function directly before bootstrap.
    # Replace only exact references in project modules, not SDK/httpx traffic.
    for name, module in list(sys.modules.items()):
        if name.startswith('evidenceguard.') and getattr(module, 'model_post', None) is original:
            module.model_post = model_post
    ops._dashboard_content_installed = True
