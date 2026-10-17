"""Bounded CPU image preprocessing; never upgrades sample provenance to decoder proof."""
import asyncio
import base64
import importlib.util
import hashlib
import json
import math
import os
from pathlib import Path
import sys

DEPTH_SHA256 = '825114de5341612386de409f82f5dfb0496bb9afa559565ac633466bf172fb71'
VERSION = 'depthart448-dis-v1'


def pair_gate(a, b, *, maximum=1.0):
    for key in ('device_id', 'channel_id', 'session_id', 'view_revision'):
        if not a.get(key) or a.get(key) != b.get(key):
            return 'VIEW_OR_SESSION_CHANGED'
    if a.get('frame_id') == b.get('frame_id'): return 'SAME_FRAME'
    for f in (a, b):
        if not f.get('source_type', '').startswith('official_live_') or f.get('freshness') != 'sampled_after_request':
            return 'LIVE_SAMPLE_REQUIRED'
    times = [f.get('sampled_at') for f in (a, b)]
    if any(type(t) not in (int, float) or not math.isfinite(t) for t in times): return 'TIME_UNKNOWN'
    if not 0 < times[1] - times[0] <= maximum: return 'FRAMES_NOT_ADJACENT'
    return None


def image_part(raw, label):
    return [dict(type='text', text=label), dict(type='image_url', image_url={
        'url': 'data:image/png;base64,' + base64.b64encode(raw).decode()})]


class LocalVision:
    def __init__(self):
        self.enabled = os.getenv('EG_LOCAL_VISION_ENABLED', '0') == '1'
        self.depth_path = os.getenv('EG_DEPTH_MODEL_PATH', '')
        self.flow_enabled = os.getenv('EG_FLOW_ENABLED', '0') == '1'
        self.guard_enabled = os.getenv('EG_GUARD_AUX_ENABLED', '0') == '1'
        self.lock = asyncio.Lock()
        self.pending = 0
        self.processes = set()
        self.closed = False
        self._model_stamp = None
        self._model_valid = False

    def configuration(self):
        deps = all(importlib.util.find_spec(m) is not None for m in ('numpy', 'cv2', 'onnxruntime'))
        try:
            path=Path(self.depth_path); stat=path.stat()
            stamp=(str(path),stat.st_mtime_ns,stat.st_size)
            if stamp!=self._model_stamp:
                self._model_valid=stat.st_size==24155097 and hashlib.sha256(path.read_bytes()).hexdigest()==DEPTH_SHA256
                self._model_stamp=stamp
        except (OSError,ValueError): self._model_valid=False
        return dict(enabled=self.enabled, ready=self.enabled and deps,
                    depthReady=self.enabled and deps and self._model_valid, depthSha256=DEPTH_SHA256,
                    flowReady=self.enabled and deps and self.flow_enabled, version=VERSION,
                    depthModel='DepthART448', flowAlgorithm='OpenCV DIS FAST',
                    execution='server_cpu_subprocess', maxParallel=1, frameIntervalLimitMs=1000,
                    decoderProofGenerated=False, metricDistance=False)

    async def analyze(self, first, last, a, b, *, depth=False, flow_pair=None):
        config = self.configuration()
        empty = dict(version=VERSION, depth=dict(status='skipped'), flow=dict(status='skipped'), images=[])
        if not config['ready'] or self.closed: return empty | {'status':'unavailable', 'code':'LOCAL_VISION_NOT_READY'}
        if depth and not config['depthReady']: return empty | {'status':'unavailable', 'code':'DEPTH_MODEL_MISSING'}
        if self.pending >= 3: return empty | {'status':'unavailable', 'code':'LOCAL_VISION_BUSY'}
        flow_a, flow_b, meta_a, meta_b = flow_pair or (first, last, a, b)
        gate = pair_gate(meta_a, meta_b) if self.flow_enabled else 'FLOW_DISABLED'
        request = dict(depth=depth, depthPath=self.depth_path, depthHash=DEPTH_SHA256,
                       images=[base64.b64encode(x).decode() for x in (first, last)],
                       flowImages=[base64.b64encode(x).decode() for x in (flow_a, flow_b)] if not gate else None)
        self.pending += 1
        acquired = False
        proc = None
        try:
            await asyncio.wait_for(self.lock.acquire(), 8)
            acquired = True
            if self.closed: return empty | {'status':'unavailable', 'code':'LOCAL_VISION_CLOSED'}
            # Separate process: a slow/crashed ONNX call cannot retain the API worker or lock.
            env = {k:v for k,v in os.environ.items() if not k.startswith(('EG_','AWS_','OPENAI_','ANTHROPIC_'))}
            env.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
            env['PYTHONPATH']=str(Path(__file__).resolve().parents[2])+os.pathsep+env.get('PYTHONPATH','')
            proc = await asyncio.create_subprocess_exec(sys.executable, '-m', 'evidenceguard.vision.worker',
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env)
            self.processes.add(proc)
            out, _ = await asyncio.wait_for(proc.communicate(json.dumps(request).encode()), 25)
            if proc.returncode or len(out) > 6_000_000: raise ValueError('worker failed')
            result = json.loads(out)
            if gate: result['flow'] = dict(status='skipped', code=gate)
            else:
                result['flow'].update(sourceFrames=[meta_a['frame_id'],meta_b['frame_id']],
                    intervalMs=round((meta_b['sampled_at']-meta_a['sampled_at'])*1000),
                    timestampMeaning='client_live_sample', decoderProgressVerified=all(bool(f.get('decoder_frame')) for f in (meta_a,meta_b)))
            result.update(version=VERSION, status='completed', controlEligible=False)
            return result
        except asyncio.CancelledError: raise
        except (TimeoutError, ValueError, OSError):
            return empty | {'status':'unavailable', 'code':'LOCAL_VISION_FAILED'}
        finally:
            if proc:
                if proc.returncode is None:
                    try: proc.kill()
                    except ProcessLookupError: pass
                    await proc.wait()
                self.processes.discard(proc)
            if acquired: self.lock.release()
            self.pending -= 1

    @staticmethod
    def parts(result):
        content = [dict(type='text', text='辅助算法结果（不代表硬件动作或米制距离）：'+json.dumps(
            {k:v for k,v in result.items() if k!='images'}, ensure_ascii=False))]
        for item in result.get('images', []):
            content += [dict(type='text',text=item['label']), dict(type='image_url', image_url={
                'url':'data:image/png;base64,'+item['base64']})]
        return content

    async def close(self):
        self.closed = True
        for proc in list(self.processes):
            if proc.returncode is None:
                try: proc.kill()
                except ProcessLookupError: pass
                await proc.wait()
