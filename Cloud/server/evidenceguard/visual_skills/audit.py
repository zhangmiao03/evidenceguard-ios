"""Best-effort guard diagnostics in the existing separate observability store.

Never schedules captures, runs inference, or changes a scene's decision. Binary
inputs are handled by the opt-in model transport observer, not by this module.
"""
import asyncio
import contextvars
import itertools
import os
import time
import uuid

from .. import ops
SEQUENCE = contextvars.ContextVar('eg_guard_sequence', default=None)


def frame_reference(frame):
    return {key: frame[key] for key in (
        'frameId', 'mediaId', 'sourceType', 'sampledAt', 'capturedAt',
        'viewRevision', 'freshnessBasis', 'status') if isinstance(frame, dict) and key in frame}


def capture_enabled(recorder):
    return bool(getattr(recorder, 'capture', False) or os.getenv('EG_DASHBOARD_CAPTURE_CONTENT') == '1')


def event(name, *, status='completed', duration=None, **data):
    recorder = ops.RECORDER.get()
    if recorder:
        try:
            counter = SEQUENCE.get()
            if counter is not None: data['guardSequence'] = next(counter)
            if not capture_enabled(recorder):
                def redact(value):
                    if isinstance(value, dict):
                        return {k: ops.text_ref(v) if k in {'reason', 'title'} else redact(v) for k, v in value.items()}
                    if isinstance(value, list): return [redact(v) for v in value]
                    return value
                data = redact(data)
            recorder.emit('guard.' + name, status=status, duration=duration, data=data)
        except Exception:
            # Even a broken recorder must not affect the original guard path.
            pass


class GuardRun:
    def __init__(self, store, scene, *, mode='live_guard'):
        self.recorder = getattr(store, 'ops', None)
        self.scene = scene
        self.id = 'guard-' + uuid.uuid4().hex
        self.mode = mode
        self.result = {}
        self.tokens = []

    def __enter__(self):
        self.start = time.monotonic()
        self.tokens = [(ops.CTX, ops.CTX.set(dict(traceId=self.id, spanId=uuid.uuid4().hex))),
                       (ops.RECORDER, ops.RECORDER.set(self.recorder)),
                       (ops.OPERATION, ops.OPERATION.set('guard.observe')),
                       (SEQUENCE, SEQUENCE.set(itertools.count(1)))]
        data = dict(runId=self.id, mode=self.mode, sceneId=self.scene.get('id'),
                    sceneRevision=self.scene.get('revision'), cameraId=self.scene.get('cameraId'),
                    reference=frame_reference(self.scene.get('frame')))
        if self.recorder and capture_enabled(self.recorder):
            data['title'] = self.scene.get('plan', {}).get('title')
        event('started', status='started', **data)
        return self

    def finish(self, **result):
        self.result = result

    def __exit__(self, kind, value, traceback):
        try:
            status = 'cancelled' if kind and issubclass(kind, asyncio.CancelledError) else 'failed' if kind else 'completed'
            event('finished', status=status, duration=round((time.monotonic()-self.start)*1000, 2),
                  runId=self.id, mode=self.mode, **self.result,
                  **({'errorType': kind.__name__} if kind else {}))
        finally:
            for variable, token in reversed(self.tokens):
                variable.reset(token)
        return False
