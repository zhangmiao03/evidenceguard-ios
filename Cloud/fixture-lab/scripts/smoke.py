"""Exercise real RTSP transport + HTTP API. Run against a disposable demo instance."""
import json
import os
from pathlib import Path
import time
import httpx

BASE=os.getenv('EG_BASE_URL','http://127.0.0.1:8787')
client=httpx.Client(base_url=BASE,timeout=5,trust_env=False)
results=[]


def state():
    r=client.get('/api/state');r.raise_for_status();return r.json()


def post(path,body):
    r=client.post(path,json=body);r.raise_for_status();return r.json()


def check(name,predicate,timeout=20):
    start=time.time()
    while time.time()-start<timeout:
        s=state()
        if s['worker']['error']:
            raise AssertionError(s['worker']['error'])
        if predicate(s):
            item={'name':name,'passed':True,'seconds':round(time.time()-start,2),
                  'result':s['task']['result'],'reason':s['task']['reason'],
                  'evidence':[o['frame_id'] for o in s['task']['evidence']]}
            results.append(item);print(json.dumps(item,ensure_ascii=False),flush=True);return s
        time.sleep(.3)
    raise AssertionError(f'{name}: timed out; task={s["task"]}; cameras={s["cameras"]}')


def scene(name,mode='continuous'):
    post('/api/simulation',{'scenario':name,'mode':mode})
    return time.time()


try:
    t=scene('normal')
    post('/api/task/action',{'action':'resume'})
    check('两路 RTSP 正常取帧并确认',lambda s:s['task']['result']=='confirmed' and all(c['fresh'] for c in s['cameras']))
    scene('occluded_a')
    check('A 遮挡后 B 新鲜证据补证',lambda s:s['task']['result']=='confirmed' and s['task']['evidence'][0]['device_id']=='cam-b')
    t=scene('hidden_both')
    check('双遮挡保持未知',lambda s:s['task']['result']=='unknown' and all(c['observation']['relation']=='unknown' and c['observation']['captured_at']>t for c in s['cameras']))
    t=scene('lookalike')
    check('相似箱子不冒充绑定目标',lambda s:s['task']['result']=='unknown' and all(c['observation']['marker_ids']==[23] for c in s['cameras']))
    scene('conflict')
    check('两个视角冲突保持未知',lambda s:s['task']['result']=='unknown' and '冲突' in s['task']['reason'])
    scene('normal')
    check('恢复正常基线',lambda s:s['task']['result']=='confirmed')
    t=scene('old_b')
    check('旧图过期不算新证据',lambda s:s['task']['result']=='unknown' and s['cameras'][1]['age']>6 and s['cameras'][1]['observation']['captured_at']<t)
    scene('moved')
    s=check('真实像素检测离区并打开告警',lambda s:s['task']['result']=='needs_attention' and s['task']['alert']=='open')
    episode=s['task']['episode']
    result=post('/api/task/action',{'action':'recheck'})
    assert result['task']['alert']=='acknowledged' and result['task']['result']=='unknown'
    check('已处理仍需新证据，区外告警不消失',lambda s:s['task']['result']=='needs_attention' and s['task']['alert']=='acknowledged' and s['task']['episode']==episode)
    scene('offline_both')
    check('双断流转未知并保留告警',lambda s:s['task']['result']=='unknown' and s['task']['alert']=='acknowledged' and all(not c['fresh'] for c in s['cameras']))
    scene('normal')
    check('双路恢复后新证据解决告警',lambda s:s['task']['result']=='confirmed' and s['task']['alert']=='resolved')
    scene('normal','event_only')
    check('事件结束后证据过期',lambda s:s['task']['result']=='unknown' and all(not c['fresh'] for c in s['cameras']))
    result=post('/api/task/action',{'action':'recheck'})
    assert result['commands'][-1]['status']=='unsupported'
    results.append({'name':'事件设备不支持主动抓拍时明确拒绝','passed':True})
    scene('normal','on_demand')
    check('按需调度取得新图并确认',lambda s:s['task']['result']=='confirmed')
    s=post('/api/task/action',{'action':'pause'})
    previous=s['task']['result']
    scene('moved')
    check('暂停时新画面不改变任务结论',lambda s:s['task']['lifecycle']=='paused' and s['task']['result']==previous and all(c['observation']['relation']=='outside' for c in s['cameras']))
    scene('normal')
    post('/api/task/action',{'action':'resume'})
    s=check('恢复任务重新获取证据',lambda s:s['task']['lifecycle']=='active' and s['task']['result']=='confirmed')
    rev=s['task']['revision']
    updated=post('/api/task',{'revision':rev,'title':s['task']['title'],'roi':s['task']['roi']})
    assert updated['task']['revision']==rev+1 and updated['task']['result']=='unknown'
    check('规则修改后仅新版本证据可确认',lambda s:s['task']['result']=='confirmed' and all(o['revision']==rev+1 for o in s['task']['evidence']))
    snapshot=state()
    for camera in snapshot['cameras']:
        image=client.get(camera['image_url']);image.raise_for_status()
        assert image.headers['content-type']=='image/jpeg' and len(image.content)>1000
    results.append({'name':'两个证据原图可读取','passed':True})
finally:
    output=Path(__file__).resolve().parent.parent/'docs'/'smoke-results.json'
    output.write_text(json.dumps({'at':time.strftime('%Y-%m-%d %H:%M:%S %z'), 'base_url':BASE,
                                 'transport':'FFmpeg -> MediaMTX 1.21.1 -> FFmpeg',
                                 'results':results},ensure_ascii=False,indent=2))
    client.close()
print(f'PASS {len(results)} end-to-end checks',flush=True)
