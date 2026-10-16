"""Explicit one-off deployment validation using the configured real model.

Creates a labelled test conversation in demo/team. Requests read-only tools;
never sends a camera-control command or reads credentials into console output.
Run on the EC2 with its existing venv. Do not schedule this as a health probe.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import uuid
import httpx
from dotenv import dotenv_values


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--environment',choices=['demo','team'],required=True)
    parser.add_argument('--require-content',action='store_true',help='Verify complete redacted bodies and the actual final App reply')
    args=parser.parse_args()
    service,port={'demo':('evidenceguard-demo',8792),'team':('evidenceguard',8790)}[args.environment]
    config=dotenv_values('/etc/'+service+'/cloud.env')
    installation=str(uuid.uuid4());request_id='dashboard-smoke-'+uuid.uuid4().hex
    with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=10,trust_env=False,
        headers={'Authorization':'Bearer '+config['EG_ACCESS_TOKEN'],'X-EG-Installation-ID':installation}) as client:
        conversation=client.post('/api/agent/conversations',json={'requestId':str(uuid.uuid4())})
        if conversation.status_code==404:
            # Older team builds create a conversation implicitly with the run.
            conversation_id='dashboard-check-'+uuid.uuid4().hex
        else:
            conversation.raise_for_status();conversation_id=conversation.json()['id']
        response=client.post('/api/agent/runs',json={'requestId':request_id,'conversationId':conversation_id,
            'message':'这是 Dashboard 部署验证请求。请依次调用 list_camera_capabilities 和 list_tasks，然后简短回复验证结果。只能查询已有设备能力和任务列表，禁止创建修改任务、取新画面、录音播放、发通知或控制设备。'})
        response.raise_for_status();run=response.json()
        deadline=time.monotonic()+130
        while time.monotonic()<deadline:
            response=client.get('/api/runs/'+run['id']);response.raise_for_status();run=response.json()
            if run['status'] in {'completed','failed','cancelled','interrupted'}:break
            time.sleep(2)
    # Read only the sanitised collector output; no application records are exported.
    for _ in range(15):
        data=json.loads(Path('/var/lib/evidenceguard-dashboard/'+args.environment+'.json').read_text())
        rows=[r for r in data['records'] if r['traceId']==run['id']]
        if any(r['name']=='agent.finished' for r in rows):break
        time.sleep(1)
    calls=[r for r in rows if r['kind']=='model']
    http_calls=[r for r in calls if r['data'].get('transport')!='codex_app_server']
    codex_steps=[r for r in calls if r['data'].get('transport')=='codex_app_server']
    tools=[r['data'].get('tool') for r in rows if r['name']=='tool.finished']
    prompts=[r for r in rows if r['kind']=='prompt']
    result={'environment':args.environment,'runId':run['id'],'status':run['status'],
        'observedHttpCalls':len(http_calls),'codexSteps':len(codex_steps),
        'models':sorted({r['data']['model'] for r in calls}),
        'httpStatuses':[r['data'].get('httpStatus') for r in http_calls], 'tools':tools,
        'promptSnapshots':len(prompts),'traceRecords':len(rows),'usageReceived':sum(bool(r['data'].get('usage')) for r in calls),
        'snapshotFresh':time.time()-data['dataset']['exportedAt']<20}
    print(json.dumps(result,ensure_ascii=True))
    assert run['status']=='completed', 'Live model run did not complete'
    assert len(calls)>=2 and len(prompts)==len(calls), 'Incomplete model-tool-model trace'
    assert {'list_camera_capabilities','list_tasks'}<=set(tools), 'Expected read-only tool receipts missing'
    assert all(r['data'].get('httpStatus')==200 for r in http_calls)
    assert all(r['status']=='executor_ok' for r in codex_steps)
    if args.require_content:
        from eg_dashboard.content import clean
        from eg_dashboard.collector import public_record, readonly
        with readonly('/var/lib/'+service+'/observability.sqlite3') as db:
            stored=[json.loads(row[0]) for row in db.execute("SELECT payload FROM records WHERE json_extract(payload,'$.traceId')=? ORDER BY at",(run['id'],))]
        projected={r['id']:public_record(r) for r in stored}
        assert all(projected.get(r['id'])==r for r in rows), 'Stored records and public projection differ'
        assert all(p['data'].get('capture',{}).get('mode')=='full_redacted' for p in prompts), 'Prompt body incomplete'
        assert all(c['data'].get('content',{}).get('response') is not None for c in calls), 'Model output missing'
        prompt_ids={p['id'] for p in prompts}
        assert all(c['data'].get('promptId') in prompt_ids for c in calls), 'Missing prompt linkage'
        if codex_steps:
            protocol=[r['data'] for r in rows if r['name']=='codex.request']
            assert {'thread/start','turn/start','item/tool/call:response'} <= {r['method'] for r in protocol}, 'Codex protocol inputs missing'
            instructions=next(r['content']['message']['params']['baseInstructions'] for r in protocol if r['method']=='thread/start')
            assert instructions, 'Actual Codex base instructions missing'
            replies=[r['data']['content']['message'] for r in rows if r['name']=='codex.response' and r['data']['method']=='item/completed']
            assert any(m['params']['item'].get('text') for m in replies), 'Actual Codex output notification missing'
            assert all(c['data'].get('wireHttpVisible') is False and c['data'].get('usage') is None for c in codex_steps), 'Codex steps mislabeled as HTTP or cumulative usage'
        assert any(any(m.get('role')=='tool' and m.get('tool_call_id') for m in p['data']['request'].get('messages',[])) for p in prompts), 'Tool results did not enter next model request'
        tool_rows=[r for r in rows if r['name']=='tool.finished']
        assert all('arguments' in r['data'].get('content',{}) and 'result' in r['data']['content'] for r in tool_rows), 'Tool body missing'
        final=next(r['data']['content']['answer'] for r in rows if r['name']=='agent.result')
        expected,_=clean(run['text'],known_secrets=[v for k,v in config.items() if v and len(v)>=8 and any(s in k.lower() for s in ('key','token','secret','password'))])
        assert final==expected, 'Final reply is not the actual runtime answer'
        encoded=json.dumps(rows,ensure_ascii=False)
        for key,value in config.items():
            if value and len(value)>=8 and any(s in key.lower() for s in ('key','token','secret','password')):
                assert value not in encoded, 'Credential found in public trace'
        proof={**result,'fullContentVerified':True,'storedProjectionMatches':True,'credentialsAbsent':True,
               'finalReplySha256':hashlib.sha256(final.encode()).hexdigest(),
               'finalReplyCharacters':len(final),'modelOutputs':len(calls),'toolBodies':len(tool_rows)}
        proof_path=Path('/var/tmp')/(run['id']+'.json')
        proof_path.write_text(json.dumps(proof,ensure_ascii=False));proof_path.chmod(0o600)
        print(json.dumps(proof,ensure_ascii=True))


if __name__=='__main__':main()
