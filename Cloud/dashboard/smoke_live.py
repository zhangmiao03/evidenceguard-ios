"""Explicit one-off deployment validation using the configured real model.

Creates a labelled test conversation in demo/team. Requests read-only tools;
never sends a camera-control command or reads credentials into console output.
Run on the EC2 with its existing venv. Do not schedule this as a health probe.
"""
import argparse
import json
from pathlib import Path
import time
import uuid
import httpx
from dotenv import dotenv_values


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--environment',choices=['demo','team'],required=True)
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
    tools=[r['data'].get('tool') for r in rows if r['name']=='tool.finished']
    prompts=[r for r in rows if r['kind']=='prompt']
    result={'environment':args.environment,'runId':run['id'],'status':run['status'],
        'realModelCalls':len(calls),'models':sorted({r['data']['model'] for r in calls}),
        'httpStatuses':[r['data'].get('httpStatus') for r in calls], 'tools':tools,
        'promptSnapshots':len(prompts),'traceRecords':len(rows),'usageReceived':sum(bool(r['data'].get('usage')) for r in calls),
        'snapshotFresh':time.time()-data['dataset']['exportedAt']<20}
    print(json.dumps(result,ensure_ascii=True))
    assert run['status']=='completed', 'Live model run did not complete'
    assert len(calls)>=2 and len(prompts)==len(calls), 'Incomplete model-tool-model trace'
    assert {'list_camera_capabilities','list_tasks'}<=set(tools), 'Expected read-only tool receipts missing'
    assert all(r['data'].get('httpStatus')==200 for r in calls)


if __name__=='__main__':main()
