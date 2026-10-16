"""Record actual retrieval arguments/results without changing search behavior."""
import asyncio
import functools
import inspect
import time
import uuid
from . import content


def observe_search(service, ops, recorder):
    original = service.search
    signature = inspect.signature(original)
    @functools.wraps(original)
    async def search(*args, **kwargs):
        old = ops.CTX.get()
        ctx = dict(traceId=old.get('traceId') or uuid.uuid4().hex,
                   spanId=uuid.uuid4().hex,parentSpanId=old.get('spanId'))
        token=ops.CTX.set(ctx); rec_token=ops.RECORDER.set(recorder)
        began=time.monotonic(); status='failed'; result=None; error=None
        arguments={}
        try:
            arguments=dict(signature.bind(*args,**kwargs).arguments)
            arguments.pop('progress',None)
        except (ValueError,TypeError):pass
        try:
            result=await original(*args,**kwargs)
            status='completed'
            return result
        except asyncio.CancelledError:
            status='cancelled';raise
        except Exception as exc:
            error=type(exc).__name__;raise
        finally:
            try:
                recorder.emit('vector.search',status=status,trace=ctx,
                    duration=round((time.monotonic()-began)*1000,2),
                    data={'inputKind':'text','query':arguments.get('query'),
                          **content.details(arguments=arguments,result=result,error=error)})
            except Exception:pass
            ops.RECORDER.reset(rec_token);ops.CTX.reset(token)
    service.search=search
