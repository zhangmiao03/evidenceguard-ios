"""Publish one deliberate draft/revision test through the real scene API.

Uses a separate installation, creates drafts only, and never requests a frame,
selection, activation or device control. The paired picture is an already public
recording frame, not an image sent to the text compiler or a live capture.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import time
import urllib.request
import uuid


def capture(config, recording_id, expected_sha):
    settings = json.loads(Path(config).read_text())
    e = settings['environments']['demo']
    state = json.loads(Path(e['state']).read_text())
    pid = subprocess.check_output(['systemctl','show',e['service'],'-p','MainPID','--value'],text=True).strip()
    assert str(state['pid']) == pid, 'Observer is stale'
    env = dict(p.split('=',1) for p in Path('/proc/'+pid+'/environ').read_text().split('\0') if '=' in p)
    from dotenv import dotenv_values
    env = {**dotenv_values(env.get('EG_ENV_FILE','/etc/evidenceguard-demo/cloud.env')), **env}
    folder = Path(settings['output'])/'briefing'/'demo'
    original = json.loads((folder/'manifest.json').read_text())
    assert original['source']['recordingId'] == recording_id and original['source']['assetId'] == expected_sha
    public = json.loads((Path(settings['output'])/'media'/'demo'/'manifest.json').read_text())
    assert expected_sha in public['items'], 'Source must already be published'
    with sqlite3.connect('file:'+e['database']+'?mode=ro',uri=True) as db:
        recording = json.loads(db.execute('SELECT payload FROM recordings WHERE id=?',(recording_id,)).fetchone()[0])
    source = Path(e['source'])/'visual_skills'/'harness.py'
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    target = folder/'skills.json'
    # Re-running deployment must not repeat paid calls or create duplicate drafts.
    if target.is_file():
        saved = json.loads(target.read_text())
        if saved.get('compilerSha256') == source_hash and saved.get('source') == original['source']:
            print(json.dumps({'status':'already_saved','revisions':len(saved.get('revisions',[]))})); return
    headers = {'Authorization':'Bearer '+env['EG_ACCESS_TOKEN'], 'X-EG-Installation-ID':str(uuid.uuid4())}
    def call(path, body=None):
        h = dict(headers)
        if body is not None: h['Content-Type']='application/json'
        req = urllib.request.Request('http://127.0.0.1:8792'+path, data=json.dumps(body).encode() if body is not None else None, headers=h)
        with urllib.request.urlopen(req,timeout=30) as response: return json.load(response)
    def finish(scene):
        deadline=time.monotonic()+100
        while scene['stage']=='generating' and time.monotonic()<deadline:
            time.sleep(1); scene=call('/api/visual-scenes/'+scene['id'])
        assert scene['status']=='draft' and not scene['canActivate']
        assert scene['stage']!='generating', 'Compiler still running; do not label this successful'
        return scene
    messages = ['帮我看着桌面上这个红盖水瓶，离开框选区域后观察30秒，只提醒一次。',
                '改成观察45秒，持续提醒，其他条件保持不变。']
    revisions=[]
    for index, message in enumerate(messages):
        start=time.monotonic()
        body={'requestId':str(uuid.uuid4()), 'message':message}
        if index == 0:
            scene=finish(call('/api/visual-scenes',body|{'cameraId':recording['cameraId']}))
        else:
            scene=finish(call('/api/visual-scenes/'+scene['id']+'/interpret',body|{'revision':scene['revision']}))
        revisions.append({k:scene[k] for k in ('id','revision','status','stage','plan','question','unsupportedReason','summary','reason','limitation','canActivate') if k in scene} |
                         {'input':message,'durationMs':round((time.monotonic()-start)*1000),'capturedAt':time.time()})
        if not scene.get('plan') or scene.get('question') or scene.get('unsupportedReason'): break
    value=dict(schema='evidenceguard.skill-case/v1', id='public-skill-'+str(int(time.time())),createdAt=time.time(),
               source=original['source'],publication='explicit_public_test',mode='real_api_draft_only',
               model=env.get('EG_MODEL_ID',''),executor=env.get('EG_AGENT_EXECUTOR','bounded-chat-v1'),
               compilerSha256=source_hash, revisions=revisions,
               referenceMedia=original['processing']['media'][:1],
               referenceOffset=original['processing']['sampleOffsets'][0])
    from eg_dashboard.content import clean,ENV_SECRET
    value,_=clean(value,known_secrets=[v for k,v in env.items() if v and ENV_SECRET.search(k) and len(v)>=8])
    pending=target.with_suffix('.pending');pending.write_text(json.dumps(value,ensure_ascii=False),encoding='utf8')
    pending.chmod(0o644);pending.replace(target)
    print(json.dumps({'status':'saved','revisions':len(revisions),'plans':[r['plan'] for r in revisions],
                      'hardwareActivated':False,'model':value['model']},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',required=True);parser.add_argument('--recording',required=True);parser.add_argument('--sha256',required=True)
    args=parser.parse_args();capture(args.config,args.recording,args.sha256)
