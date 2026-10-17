"""One-off demo validation with real read-only model calls (no hardware actions).

Credentials remain on the EC2. Creates labelled test runs for ios/web request
contracts; this does not claim an iPhone binary or camera has run on hardware.
"""
import json
from pathlib import Path
import time
import uuid

import httpx
from dotenv import dotenv_values


def verify_receipts(run, events, rows):
    """Report only evidence available for the selected executor, without fallback."""
    expected = {'list_camera_capabilities', 'list_tasks'}
    assert run['status'] == 'completed', 'Agent did not complete'
    assert not any(run.get(key) for key in ('hardwareOperations', 'captures', 'draft')), 'Unexpected write/capture'
    receipts = run.get('toolReceipts', [])
    assert {r['tool'] for r in receipts} == expected, 'Unexpected or missing tool'
    assert all(r['status'] == 'completed' for r in receipts), 'Tool did not complete'
    executor = run.get('executionContract', {}).get('executor', 'bounded-chat-v1')
    observed_tools = {r['data'].get('tool') for r in rows if r['name'] == 'tool.finished'}
    assert expected == observed_tools, 'Observer tool receipts missing or unexpected'
    if executor == 'codex-app-server-v1':
        for kind in ('executor_started', 'executor_completed'):
            assert any(e['type'] == kind and e['payload'].get('executor') == executor for e in events), 'Codex lifecycle receipt missing'
        assert any(e['type'] == 'response_completed' for e in events), 'Final response receipt missing'
        # Model HTTP runs inside Codex, outside the Python provider observer.
        # Lifecycle/tool receipts do not establish an HTTP request count/status.
        return dict(executor=executor, realModelCalls=None, modelHttpObservation='not observed by Python provider bridge',
                    codexLifecycleVerified=True, tools=sorted(expected))
    assert executor == 'bounded-chat-v1', 'Unreviewed executor'
    calls = [r for r in rows if r['kind'] == 'model']
    assert len(calls) >= 2 and all(r['data'].get('httpStatus') == 200 for r in calls), 'Model HTTP receipt missing/failed'
    return dict(executor=executor, realModelCalls=len(calls), models=sorted({r['data']['model'] for r in calls}),
                modelHttpObservation='Python provider bridge', tools=sorted(expected))


def main():
    config=dotenv_values('/etc/evidenceguard-demo/cloud.env')
    results=[]
    with httpx.Client(base_url='http://127.0.0.1:8792',timeout=12,trust_env=False) as client:
        for path in ('/api/bootstrap','/api/hardware/snapshot','/api/sdk/events'):
            assert client.get(path).status_code==401
        for path in ('/','/sdk/index.js','/official-demo/index.html'):
            assert client.get(path).status_code==200
        client.headers['Authorization']='Bearer '+config['EG_ACCESS_TOKEN']
        for platform in ('ios','web'):
            client.headers['X-EG-Installation-ID']=str(uuid.uuid4())
            client.put('/api/personal/memory-options?enabled=false').raise_for_status()
            bootstrap=client.get('/api/bootstrap');bootstrap.raise_for_status()
            hardware=client.get('/api/hardware/snapshot');hardware.raise_for_status()
            events=client.get('/api/sdk/events');events.raise_for_status()
            assert isinstance(events.json()['events'],list)
            assert client.get('/api/camera-observation').status_code==200
            topic=client.post('/api/agent/conversations',json={'requestId':str(uuid.uuid4())});topic.raise_for_status()
            conversation=topic.json()['id']
            client.patch('/api/agent/conversations/'+conversation,json={'title':'联调验证 · '+platform+' · 只读'}).raise_for_status()
            rid='demo-toolchain-'+platform+'-'+uuid.uuid4().hex
            client.headers['X-EG-Trace-ID']=rid
            response=client.post('/api/agent/runs',json={'requestId':rid,'conversationId':conversation,'clientPlatform':platform,
                'message':'这是部署联调验证。请调用 list_camera_capabilities 和 list_tasks，然后简短说明结果。仅查询已有设备与任务，不创建修改任务、不取画面、不控制设备、不发通知。'})
            response.raise_for_status()
            for _ in range(85):
                response=client.get('/api/runs/'+rid);response.raise_for_status();run=response.json()
                if run['status'] in {'completed','failed','cancelled','interrupted'}:break
                time.sleep(2)
            assert run['status']=='completed', 'Agent run failed: '+rid
            assert run['clientPlatform']==platform
            event_response=client.get('/api/runs/'+rid+'/events');event_response.raise_for_status()
            for _ in range(20):
                snapshot=json.loads(Path('/var/lib/evidenceguard-dashboard/demo.json').read_text())
                rows=[r for r in snapshot['records'] if r['traceId']==rid]
                if any(r['name']=='agent.finished' for r in rows):break
                time.sleep(1)
            verified=verify_receipts(run,event_response.json(),rows)
            results.append({'platformContract':platform,'runId':rid,'status':run['status'],**verified,
                'registeredDevices':len(bootstrap.json()['cameras']),
                'executorDevices':len(hardware.json()['devices']),'promptSnapshots':sum(r['kind']=='prompt' for r in rows),
                'physicalHardwareVerified':False})
    print(json.dumps({'environment':'demo','checks':results},ensure_ascii=True))


if __name__=='__main__':main()
