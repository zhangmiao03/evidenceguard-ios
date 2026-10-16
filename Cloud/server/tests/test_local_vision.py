"""Real CPU algorithms on synthetic pixels; no physical-camera claims."""
import asyncio
import base64
import io
import time
from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image
from evidenceguard.vision.processing import LocalVision, pair_gate
from evidenceguard.camera.contracts import FrameRef
from evidenceguard.camera.live import LiveDevices
from evidenceguard.store import Store


def meta(key,at):
    return dict(device_id='sdk-test',channel_id='main',session_id='s1',view_revision='s1:0',
        frame_id=key,source_type='official_live_ios',freshness='sampled_after_request',sampled_at=at,
        captured_at=None,received_at=at)


@pytest.mark.parametrize('field,value,code',[
    ('session_id','s2','VIEW_OR_SESSION_CHANGED'),('channel_id','lower','VIEW_OR_SESSION_CHANGED'),
    ('device_id','other','VIEW_OR_SESSION_CHANGED'),('view_revision','s1:1','VIEW_OR_SESSION_CHANGED'),
    ('frame_id','a','SAME_FRAME'),('sampled_at',30,'FRAMES_NOT_ADJACENT'),
    ('sampled_at',float('nan'),'TIME_UNKNOWN'),('source_type','uploaded','LIVE_SAMPLE_REQUIRED')])
def test_flow_never_interpolates_invalid_pairs(field,value,code):
    a,b=meta('a',10),meta('b',10.5);b[field]=value
    assert pair_gate(a,b)==code


def test_buffer_is_bounded_and_never_invents_decoder_evidence(tmp_path):
    store=Store(tmp_path/'buffer.sqlite'); live=LiveDevices(store); now=time.time()
    for i in range(30):
        f=FrameRef(**meta(str(i),now-3+i*.1))
        live.frames[f.frame_id]=(f,b'image-'+str(i).encode(),'image/jpeg')
    live.trim_frames()
    assert len(live.frames)==12
    pair=live.recent_pair('sdk-test','29')
    assert pair[2]['frame_id']=='28' and pair[3]['frame_id']=='29'
    assert pair[2]['decoder_frame'] is None
    assert live.recent_pair('other','29') is None
    frame,raw,mime=live.frames['29'];live.frames['29']=(replace(frame,view_revision='s1:2'),raw,mime)
    assert live.recent_pair('sdk-test','29') is None
    store.close()


def pixels():
    import numpy as np
    rng=np.random.default_rng(120)
    a=rng.integers(0,256,(160,240,3),dtype=np.uint8)
    b=np.roll(a,3,axis=1)
    result=[]
    for im in (a,b):
        buf=io.BytesIO();Image.fromarray(im).save(buf,format='PNG');result.append(buf.getvalue())
    return result


def test_real_dis_reports_pixels_and_rejects_repeated_or_mismatched_images():
    pytest.importorskip('cv2');pytest.importorskip('onnxruntime')
    from evidenceguard.vision.worker import decode,optical_flow
    a,b=[decode(base64.b64encode(x)) for x in pixels()]
    result,_=optical_flow(a,b)
    assert result['status']=='completed' and result['units']=='pixels_per_pair'
    assert abs(result['backgroundTranslationCandidate'][0]-3)<1
    assert optical_flow(a,a)[0]['code']=='REPEATED_PIXELS_NOT_PROOF_OF_STILLNESS'
    assert optical_flow(a,b[:100])[0]['code']=='DIMENSIONS_CHANGED'


def test_real_depth_and_flow_subprocess_is_bounded_and_metadata_honest(monkeypatch):
    pytest.importorskip('cv2');pytest.importorskip('onnxruntime')
    path=Path(__file__).resolve().parents[2]/'vision-resource-lab/models/depthart448.onnx'
    if not path.exists() or path.stat().st_size!=24155097: pytest.skip('Pinned LFS model not downloaded in this job')
    monkeypatch.setenv('EG_LOCAL_VISION_ENABLED','1');monkeypatch.setenv('EG_FLOW_ENABLED','1')
    monkeypatch.setenv('EG_DEPTH_MODEL_PATH',str(path))
    async def run():
        local=LocalVision();a,b=pixels()
        result=await local.analyze(a,b,meta('a',10),meta('b',10.5),depth=True)
        assert result['status']=='completed' and result['depth']['status']=='completed'
        assert result['flow']['status']=='completed' and result['flow']['intervalMs']==500
        assert not result['flow']['decoderProgressVerified'] and not result['controlEligible']
        assert result['depth']['metricDistance'] is False and len(result['images'])>=2
        assert not local.processes and local.pending==0
        await local.close()
    asyncio.run(run())


def test_flow_resolution_change_is_rejected_before_common_resize():
    pytest.importorskip('cv2');pytest.importorskip('onnxruntime')
    from evidenceguard.vision.worker import run
    images=[]
    for size in ((720,480),(1440,960)):
        buffer=io.BytesIO();Image.new('RGB',size,'blue').save(buffer,format='PNG')
        images.append(base64.b64encode(buffer.getvalue()).decode())
    result=run(dict(depth=False,flowImages=images))
    assert result['flow']['code']=='DIMENSIONS_CHANGED' and not result['images']


def test_bad_weight_is_not_reported_ready(tmp_path,monkeypatch):
    monkeypatch.setenv('EG_LOCAL_VISION_ENABLED','1')
    p=tmp_path/'bad.onnx';p.write_bytes(b'not weights');monkeypatch.setenv('EG_DEPTH_MODEL_PATH',str(p))
    assert not LocalVision().configuration()['depthReady']


def test_worker_timeout_kills_process_and_releases_capacity(monkeypatch):
    class Process:
        returncode=None
        killed=False
        async def communicate(self,*args):await asyncio.sleep(30)
        def kill(self):self.killed=True;self.returncode=-9
        async def wait(self):return self.returncode
    proc=Process()
    monkeypatch.setattr(asyncio,'create_subprocess_exec',AsyncMock(return_value=proc))
    real_wait=asyncio.wait_for
    async def short_wait(awaitable,timeout):return await real_wait(awaitable,.01 if timeout==25 else timeout)
    monkeypatch.setattr(asyncio,'wait_for',short_wait)
    async def run():
        local=LocalVision();local.configuration=lambda:dict(ready=True,depthReady=True)
        result=await local.analyze(b'a',b'b',meta('a',1),meta('b',1.5))
        assert result['code']=='LOCAL_VISION_FAILED' and proc.killed
        assert local.pending==0 and not local.lock.locked()
    asyncio.run(run())


def test_profile_reuses_only_explicit_current_video_config(monkeypatch,tmp_path):
    from evidenceguard.vision.endpoints import EndpointVisionService
    monkeypatch.setenv('EG_ENDPOINT_PROFILE','video');monkeypatch.setenv('EG_ENDPOINT_ENABLED','1')
    for k,v in [('BASE_URL','https://current.invalid/v1'),('MODEL_ID','current-vision'),('API_KEY','current-private-test')]:
        monkeypatch.setenv('EG_VIDEO_'+k,v)
        monkeypatch.setenv('EG_ENDPOINT_'+k,'old-dedicated-test')
    store=Store(tmp_path/'profile.sqlite')
    service=EndpointVisionService(store,SimpleNamespace())
    assert service.port.model=='current-vision' and service.port.key=='current-private-test'
    assert service.port.base_url=='https://current.invalid/v1'
    assert 'current-private-test' not in str(service.configuration())
    store.close()
