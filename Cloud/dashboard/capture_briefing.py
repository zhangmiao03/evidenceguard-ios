"""Capture an explicitly public, reproducible case from an already published video.

Run on the server with its deployed venv. Does not restart services or change
camera state. Auth stays in memory; ordinary private searches remain private.
Writes a separate allowlisted artifact for the read-only dashboard collector.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import time
import urllib.request
import uuid


def capture(config, environment, recording_id, expected_sha):
    settings = json.loads(Path(config).read_text())
    e = settings['environments'][environment]
    state = json.loads(Path(e['state']).read_text())
    pid = subprocess.check_output(['systemctl', 'show', e['service'], '-p', 'MainPID', '--value'], text=True).strip()
    assert str(state['pid']) == pid, 'Observer state is not from the running process'
    env = dict(p.split('=', 1) for p in Path('/proc/'+pid+'/environ').read_bytes().decode().split('\0') if '=' in p)
    from dotenv import dotenv_values
    env = {**dotenv_values(env.get('EG_ENV_FILE','/etc/evidenceguard-demo/cloud.env')), **env}
    db = sqlite3.connect('file:'+e['database']+'?mode=ro', uri=True)
    record = json.loads(db.execute('SELECT payload FROM recordings WHERE id=?', (recording_id,)).fetchone()[0])
    root = Path(state['videoRoot']).resolve()
    video = (root/recording_id/'playback.mp4').resolve()
    assert video.is_relative_to(root) and not video.is_symlink()
    digest = hashlib.sha256(video.read_bytes()).hexdigest()
    assert digest == expected_sha
    public = Path(settings['output'])/'media'/environment/'manifest.json'
    assert digest in json.loads(public.read_text())['items'], 'Only an already published source is permitted'
    out = Path(settings['output'])/'briefing'/environment
    out.mkdir(parents=True, exist_ok=True)
    out.chmod(0o755)
    stamp = time.time()
    api = 'http://127.0.0.1:8792'
    assert environment == 'demo', 'This capture is scoped to the competition demo'
    headers = {'Authorization':'Bearer '+env['EG_ACCESS_TOKEN'], 'X-EG-Installation-ID':str(uuid.uuid4()),
               'X-EG-Private-Key':secrets.token_urlsafe(40)}
    def call(path, body=None, raw=None):
        h = dict(headers)
        data = raw
        if body is not None: data=json.dumps(body).encode(); h['Content-Type']='application/json'
        request = urllib.request.Request(api+path, data=data, headers=h)
        with urllib.request.urlopen(request, timeout=30) as response: return json.load(response)
    def asset(raw, mime, label):
        sha = hashlib.sha256(raw).hexdigest()
        filename=sha+('.png' if mime=='image/png' else '.jpg')
        target=out/filename; target.write_bytes(raw); target.chmod(0o644)
        return dict(assetId=sha, mime=mime, label=label)

    # Read actual capability status through the authenticated running API.
    status=call('/api/vision/status')
    # The source is a saved video: this is offline preprocessing, never forged
    # official_live metadata or a claimed decoder/hardware acceptance test.
    samples=[]
    offsets=(36.,36.5)
    for offset in offsets:
        raw=subprocess.check_output(['ffmpeg','-v','error','-ss',str(offset),'-i',str(video),'-frames:v','1','-vf','scale=640:-2','-f','image2pipe','-vcodec','mjpeg','-threads','1','-'],timeout=20)
        samples.append(raw)
    worker_env={k:v for k,v in os.environ.items() if not k.startswith(('EG_','AWS_','OPENAI_','ANTHROPIC_'))}
    worker_env.update(PYTHONPATH=str(Path(e['source']).parent),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
    request=dict(depth=True,depthPath=env['EG_DEPTH_MODEL_PATH'],depthHash=status['local']['depthSha256'],
                 images=[base64.b64encode(x).decode() for x in samples],flowImages=[base64.b64encode(x).decode() for x in samples])
    result=subprocess.run([sys.executable,'-m','evidenceguard.vision.worker'],input=json.dumps(request).encode(),capture_output=True,env=worker_env,timeout=30)
    assert result.returncode == 0, 'Deployed preprocessing worker failed'
    processed=json.loads(result.stdout)
    pictures=[asset(raw,'image/jpeg',f'原录像 {offset:.1f} 秒') for raw,offset in zip(samples,offsets)]
    pictures += [asset(base64.b64decode(item['base64'],validate=True),'image/png',item['label']) for item in processed.pop('images')]
    counts={table:db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('endpoint_analyses','visual_controls')}
    package=dict(schema='evidenceguard.briefing/v1',id='briefing-'+str(int(stamp)),createdAt=stamp,servicePid=int(pid),
        source=dict(recordingId=recording_id,assetId=digest,title=record['title'],sourceType=record.get('sourceType'),duration=record['duration']),
        localVision=status['local'],endpointConfiguration=status['endpoint'],countsAtCapture=counts,
        processing=dict(mode='stored_video_replay',sampleOffsets=list(offsets),intervalMs=500,
                        liveGateApplied=False,controlEligible=False,**processed,media=pictures),searches=[])
    for text, reference in [('找出有人拿起桌面水瓶的片段',False),('查找与参考图中水瓶外观相似的目标',True)]:
        body=dict(text=text,camera_ids=[record['cameraId']],time_range={'period':'all'},limit=3,verify_limit=2)
        reference_media=[]
        if reference:
            body['image_ref']=call('/api/video-search-images',raw=samples[0])['image_ref']
            # The server normalizes JPEG inputs. Publish those exact normalized
            # bytes, not the visually similar pre-upload source frame.
            with urllib.request.urlopen(urllib.request.Request(api+'/api/video-search-images/'+body['image_ref'],headers=headers),timeout=20) as response:
                reference_media=[asset(response.read(),'image/jpeg','图文查询实际输入 · 服务端规范化参考帧')]
        job=call('/api/video-search',body=body)
        deadline=time.monotonic()+165
        while job['status'] in ('searching','verifying') and time.monotonic()<deadline:
            time.sleep(1);job=call('/api/video-search/'+job['id'])
        # This exact test is approved for publication. Never export other jobs,
        # private query-image IDs, ownership, credentials or filesystem paths.
        fields=('id','status','createdAt','reason','scope','timings','metrics','candidateCount','verifiedCount','candidateWindows','videos','querySignature','indexSignature','indexChanged')
        item={k:job[k] for k in fields if k in job}
        item.update(text=text,queryType='image_text' if reference else 'text',embeddingModel=state['models'].get('embedding'),
                    verificationModel=state['models'].get('image'),referenceMedia=reference_media)
        for v in item.get('videos',[]):
            assert v['recordingId']==recording_id, 'Unexpected source: do not publish this case'
            v.pop('playbackUrl',None);v.pop('thumbnailUrl',None);v.pop('cameraId',None)
        item.get('scope',{}).pop('cameraIds',None)
        package['searches'].append(item)
    # Capture exact association counts without returning private content.
    obs=sqlite3.connect('file:'+e['observations']+'?mode=ro',uri=True)
    table='critical_records' if obs.execute("SELECT 1 FROM sqlite_master WHERE name='critical_records'").fetchone() else 'records'
    prompts=[json.loads(row[0]) for row in obs.execute('SELECT payload FROM '+table+" WHERE json_extract(payload,'$.kind')='prompt' AND json_array_length(payload,'$.data.inputMedia')>0")]
    matching=0;images=0
    for payload, in db.execute('SELECT payload FROM evidence'):
        value=json.loads(payload);mid=value.get('imageUrl','').removeprefix('/api/media/')
        media=db.execute('SELECT bytes FROM media WHERE id=?',(mid,)).fetchone()
        if not media:continue
        images+=1;sha=hashlib.sha256(media[0]).hexdigest()
        if any(any(m.get('assetId')==sha for m in p.get('data',{}).get('inputMedia',[]) if isinstance(m,dict)) for p in prompts):matching+=1
    package['associationAudit']=dict(images=images,exactPromptMatches=matching,retainedImagePrompts=len(prompts))
    # Redact actual secret values as well as credential-shaped fields.
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    from eg_dashboard.content import clean,ENV_SECRET
    clean_package,_=clean(package,budget=1_000_000,known_secrets=[v for k,v in env.items() if ENV_SECRET.search(k) and len(v)>=8])
    target=out/'manifest.json';pending=out/'manifest.pending'
    pending.write_text(json.dumps(clean_package,ensure_ascii=False),encoding='utf8');pending.chmod(0o644);pending.replace(target)
    print(json.dumps(dict(status='saved',images=len(pictures),searches=[dict(status=x['status'],candidates=x['candidateCount'],verified=x['verifiedCount']) for x in package['searches']],associationAudit=package['associationAudit'],processing={k:v for k,v in processed.items() if k!='images'})))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',required=True);parser.add_argument('--environment',default='demo')
    parser.add_argument('--recording',required=True);parser.add_argument('--sha256',required=True)
    args=parser.parse_args();capture(args.config,args.environment,args.recording,args.sha256)
