"""CPU worker adapted from the team's SeedLite v3 preprocessing; see UPSTREAM.md."""
import base64
import hashlib
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np
import onnxruntime as ort


def decode(value, *, resize=True):
    raw = base64.b64decode(value, validate=True)
    if len(raw)>5_000_000: raise ValueError('image too large')
    im = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if im is None or im.shape[0]*im.shape[1]>16_000_000: raise ValueError('invalid image')
    factor=min(1.,640/max(im.shape[:2]))
    if resize and factor<1: im=cv2.resize(im,(round(im.shape[1]*factor),round(im.shape[0]*factor)),interpolation=cv2.INTER_AREA)
    if min(im.shape[:2])<48: raise ValueError('image too small')
    return im


def png(im, label):
    ok, data=cv2.imencode('.png', im)
    if not ok: raise ValueError('encode failed')
    return dict(label=label,base64=base64.b64encode(data).decode())


def depth_maps(images, path, expected):
    path=Path(path)
    if path.stat().st_size!=24155097 or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
        raise ValueError('depth weights integrity')
    opts=ort.SessionOptions(); opts.intra_op_num_threads=1; opts.inter_op_num_threads=1
    opts.add_session_config_entry('session.intra_op.allow_spinning','0')
    session=ort.InferenceSession(str(path),sess_options=opts,providers=['CPUExecutionProvider'])
    maps=[]
    for label, im in zip(('a','b'),images):
        rgb=cv2.cvtColor(im,cv2.COLOR_BGR2RGB)
        rgb=cv2.resize(rgb,(448,448),interpolation=cv2.INTER_CUBIC).astype(np.float32)/255.
        tensor=(rgb-np.array([.485,.456,.406],np.float32))/np.array([.229,.224,.225],np.float32)
        tensor=np.ascontiguousarray(tensor.transpose(2,0,1)[None])
        values=session.run(None,{session.get_inputs()[0].name:tensor})[0].squeeze().astype(np.float32)
        if values.ndim!=2 or not np.isfinite(values).all() or np.ptp(values)<1e-6: raise ValueError('invalid depth')
        low,high=np.percentile(values,[2,98])
        gray=np.uint8(np.clip((values-low)/max(high-low,1e-6),0,1)*255)
        maps.append(png(cv2.resize(gray,(im.shape[1],im.shape[0])),f'{label} 同帧相对逆深度：近亮远暗；独立归一化，不得跨图比较亮度或推断米数'))
    return maps


def optical_flow(a,b):
    if a.shape!=b.shape: return dict(status='skipped',code='DIMENSIONS_CHANGED'),[]
    if np.array_equal(a,b): return dict(status='skipped',code='REPEATED_PIXELS_NOT_PROOF_OF_STILLNESS'),[]
    ga,gb=(cv2.cvtColor(x,cv2.COLOR_BGR2GRAY) for x in (a,b))
    engine=cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_FAST)
    forward=engine.calc(ga,gb,None); backward=engine.calc(gb,ga,None)
    if not np.isfinite(forward).all() or not np.isfinite(backward).all(): raise ValueError('invalid flow')
    h,w=ga.shape; yy,xx=np.mgrid[:h,:w].astype(np.float32)
    tx,ty=xx+forward[:,:,0],yy+forward[:,:,1]
    inside=(tx>=1)&(tx<w-1)&(ty>=1)&(ty<h-1)
    error=np.linalg.norm(forward+cv2.remap(backward,tx,ty,cv2.INTER_LINEAR),axis=2)
    consistent=inside&(error<=np.maximum(1.5,.05*np.linalg.norm(forward,axis=2)))
    sift=cv2.SIFT_create(nfeatures=800)
    ka,da=sift.detectAndCompute(ga,None); kb,db=sift.detectAndCompute(gb,None)
    inliers=0; disagreement=None
    if da is not None and db is not None:
        matches=[p[0] for p in cv2.BFMatcher().knnMatch(da,db,k=2) if len(p)==2 and p[0].distance<.7*p[1].distance]
        if len(matches)>=8:
            pa=np.float32([ka[m.queryIdx].pt for m in matches]); pb=np.float32([kb[m.trainIdx].pt for m in matches])
            _,mask=cv2.findHomography(pa,pb,cv2.RANSAC,3.)
            if mask is not None:
                selected=mask.ravel().astype(bool); inliers=int(selected.sum())
                if inliers:
                    xy=np.rint(pa[selected]).astype(int); xy[:,0]=np.clip(xy[:,0],0,w-1); xy[:,1]=np.clip(xy[:,1],0,h-1)
                    disagreement=float(np.median(np.linalg.norm(forward[xy[:,1],xy[:,0]]-(pb-pa)[selected],axis=1)))
    passed=consistent.mean()>=.5 and inliers>=12 and disagreement is not None and disagreement<=10
    background=np.median(forward[12:-12,12:-12].reshape(-1,2),axis=0)
    info=dict(status='completed',quality='diagnostic_checks_passed_not_ground_truth' if passed else 'unreliable_for_object_motion',
        consistentFraction=float(consistent.mean()),geometricInliers=inliers,denseSparseDisagreementPx=disagreement,
        backgroundTranslationCandidate=background.tolist(),units='pixels_per_pair',
        limitation='背景中位数只是平移候选，不是相机姿态或目标追踪；不能据此操作电机。')
    canvas=a.copy()
    if passed:
        for y in range(12,h-12,24):
            for x in range(12,w-12,24):
                dx,dy=forward[y,x]
                if np.hypot(dx,dy)>=.75: cv2.arrowedLine(canvas,(x,y),(round(x+dx),round(y+dy)),(0,255,255),1,tipLength=.3)
    return info,[png(canvas,'相邻取样的 DIS 原始光流箭头：x向右、y向下，仅辅助诊断')] if passed else []


def run(request):
    cv2.setNumThreads(1)
    started=time.monotonic(); result=dict(depth=dict(status='skipped'),flow=dict(status='skipped'),images=[])
    if request['depth']:
        result['images']+=depth_maps([decode(v) for v in request['images']],request['depthPath'],request['depthHash'])
        result['depth']=dict(status='completed',model='DepthART448',sha256=request['depthHash'],normalization='independent_per_frame_p2_p98',metricDistance=False)
    if request.get('flowImages'):
        originals=[decode(v,resize=False) for v in request['flowImages']]
        if originals[0].shape!=originals[1].shape:
            result['flow']=dict(status='skipped',code='DIMENSIONS_CHANGED')
        else:
            result['flow'],pictures=optical_flow(*(decode(v) for v in request['flowImages']))
            result['images']+=pictures
    result['latencyMs']=round((time.monotonic()-started)*1000)
    return result


if __name__=='__main__':
    try:
        raw=sys.stdin.buffer.read(30_000_001)
        if len(raw)>30_000_000: raise ValueError('request too large')
        print(json.dumps(run(json.loads(raw))))
    except Exception:
        # No source bytes, paths, credentials or model text in worker errors.
        sys.exit(1)
