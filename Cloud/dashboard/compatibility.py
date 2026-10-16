"""Run against an installed backend inside an isolated temporary database.

Uses a simulated HTTP model transport, never production credentials or hardware.
Does not copy the deployed source, mutate production data, or start workers.
"""
import asyncio
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import sys
import tempfile


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--capture-content',action='store_true')
    capture=parser.parse_args().capture_content
    with tempfile.TemporaryDirectory(prefix='eg-observer-test-') as temp, ExitStack() as cleanup:
        for key in list(os.environ):
            if key.startswith('EG_'):del os.environ[key]
        os.environ.update(EG_DATABASE=temp+'/global.sqlite3',EG_OPS_DATABASE=temp+'/ops.sqlite3',
            EG_OPS_ENABLED='1',EG_OPS_CAPTURE_CONTENT='0',EG_DISABLE_WORKERS='1',
            EG_ACCESS_TOKEN='compatibility-only-'+('x'*40),EG_MODEL_BASE_URL='https://model.invalid/v1',
            EG_MODEL_ID='compatibility-transport',EG_MODEL_API_KEY='compatibility-placeholder',
            EG_MEDIA_ROOT=temp+'/media')
        os.environ['EG_DASHBOARD_CAPTURE_CONTENT']='1' if capture else '0'
        import httpx
        requests=[];final_run={}
        original_post=httpx.AsyncClient.post
        async def simulated_post(self,url,*args,**kwargs):
            if str(url)=='https://sdk.invalid/device':
                return httpx.Response(200,json={'status':'sdk-response'},request=httpx.Request('POST',url))
            assert str(url)=='https://model.invalid/v1/chat/completions','Unexpected external request in compatibility test'
            body=kwargs['json'];requests.append(json.loads(json.dumps(body)))
            message={'role':'assistant','content':'Compatibility check complete.'} if len(requests)>1 else {
                'role':'assistant','content':None,'tool_calls':[{'id':'call-test','type':'function','function':{'name':'list_camera_capabilities','arguments':'{}'}}]}
            return httpx.Response(200,json={'choices':[{'message':message}],'usage':{'prompt_tokens':8,'completion_tokens':4,'total_tokens':12}},headers={'x-request-id':'compat-request-'+str(len(requests))},request=httpx.Request('POST',url))
        httpx.AsyncClient.post=simulated_post
        from eg_dashboard.bridge import load_ops, instrument, attach
        ops,native=load_ops();instrument(ops,native)
        from evidenceguard.app import create_app, app as global_app
        cleanup.callback(global_app.state.store.db.close)
        if hasattr(global_app.state,'hardware'):
            cleanup.callback(lambda: asyncio.run(global_app.state.hardware.close()))
        if getattr(global_app.state.store,'ops',None):
            global_app.state.store.ops.close()
        app=attach(create_app(db_path=Path(temp)/'business.sqlite3',start_worker=False),ops,native)
        cleanup.callback(app.state.store.db.close)
        cleanup.callback(app.state.store.ops.close)
        if hasattr(app.state,'hardware'):
            cleanup.callback(lambda: asyncio.run(app.state.hardware.close()))
        from fastapi.testclient import TestClient
        from evidenceguard.harness.tools import ToolRegistry, Arguments
        class Named(Arguments):name:str
        async def named(name):return {'name':name}
        async def checks():
            registry=ToolRegistry();registry.register('named_tool',named,Named)
            token=ops.RECORDER.set(app.state.store.ops);ctx=ops.CTX.set({'traceId':'tool-compat','spanId':'parent'})
            try:
                assert await registry.call('named_tool',name='preserved')=={'name':'preserved'}
                try:await registry.call('not_authorized')
                except ValueError:pass
                else:raise AssertionError('Unknown tool became authorized')
                async with httpx.AsyncClient() as unrelated:
                    response=await unrelated.post('https://sdk.invalid/device',json={'model':'T8171'})
                    assert response.json()=={'status':'sdk-response'}
                run=app.state.agent.start('仅列出摄像头能力，不操作硬件。','compatibility-conversation',request_id='compatibility-run')
                for _ in range(200):
                    await asyncio.sleep(.02)
                    current=app.state.store.run(run['id'])
                    if current['status'] in {'completed','failed','cancelled'}:break
                assert current['status']=='completed', 'Agent loop did not complete'
                assert len(requests)==2,'Expected model -> tool -> model'
                assert any(m.get('role')=='tool' for m in requests[1]['messages'])
                final_run.update(current)
            finally:
                ops.CTX.reset(ctx);ops.RECORDER.reset(token)
                await app.state.agent.shutdown()
        # ASGI transport tests do not enter lifespan or start any background workers.
        client=TestClient(app)
        assert client.get('/api/health').status_code==200
        assert client.get('/api/bootstrap').status_code==401
        bootstrap=client.get('/api/bootstrap',headers={'Authorization':'Bearer '+os.environ['EG_ACCESS_TOKEN']})
        assert bootstrap.status_code==200
        assert isinstance(bootstrap.json()['cameras'],list)
        display_path='/api/ops/display-receipts'
        receipt=dict(id='display-check',runId='compatibility-run',backendTextHash='a'*64,displayTextHash='b'*64,
                     presentationVersion='test-v1',appVersion='compatibility',platform='ios',status='completed')
        assert client.post(display_path,json=receipt).status_code==401, 'Display receipt lost App authentication'
        headers={'Authorization':'Bearer '+os.environ['EG_ACCESS_TOKEN'],'X-EG-Installation-ID':'compatibility-client'}
        assert client.post(display_path,json={**receipt,'body':'forbidden'},headers=headers).status_code==422
        receipt['runId']='display-only-test'
        assert client.post(display_path,json=receipt,headers=headers).json()['accepted']==1
        asyncio.run(checks());app.state.store.ops.flush()
        rows=app.state.store.ops.bundle()['records']
        linked=[r for r in rows if r['traceId']=='compatibility-run']
        assert not any(r['kind']=='model' and r['traceId']=='tool-compat' for r in rows), 'SDK model field was counted as an AI request'
        assert sum(r['kind']=='model' for r in linked)==2, 'Model observations are missing or doubled'
        assert sum(r['kind']=='prompt' for r in linked)==2
        assert any(r['name']=='tool.finished' for r in linked)
        assert any(r['name']=='agent.result' for r in linked)
        assert any(r['name']=='agent.finished' and r['status']=='completed' for r in linked)
        assert 'compatibility-placeholder' not in json.dumps(rows)
        with app.state.store.ops.lock:
            critical=app.state.store.ops.db.execute('SELECT count(*) FROM critical_records').fetchone()[0]
        assert critical>0, 'Separate Agent retention unavailable'
        if capture:
            from eg_dashboard.collector import public_record
            public=[public_record(r) for r in linked]
            prompts=[r['data'] for r in public if r['kind']=='prompt']
            models=[r['data'] for r in public if r['kind']=='model']
            assert all(p['capture']['mode']=='full_redacted' for p in prompts)
            assert prompts[0]['request']['messages'][0]['content']==requests[0]['messages'][0]['content']
            assert any(m.get('tool_call_id')=='call-test' for m in prompts[1]['request']['messages'])
            assert models[1]['content']['response']['choices'][0]['message']['content']=='Compatibility check complete.'
            assert all(m['providerRequestId'].startswith('compat-request-') for m in models)
            assert all(m['usage']['total_tokens']==12 for m in models)
            tools=[r['data']['content'] for r in public if r['name']=='tool.finished']
            assert tools and all('arguments' in t and 'result' in t for t in tools)
            result=next(r['data']['content'] for r in public if r['name']=='agent.result')
            assert result['answer']==final_run['text'], 'Final App answer differs from captured result'
            assert 'compatibility-placeholder' not in json.dumps(public)
        print(json.dumps({'ok':True,'nativeOps':native,'appVersion':app.version,'simulatedModelRequests':len(requests),
                          'linkedRecords':len(linked),'fullContent':capture,'assertions':['health','API authentication','camera listing','tool name argument','unauthorized tool rejection','model-tool-model loop','prompt linkage','no duplicate HTTP observations','full body linkage when enabled']}))
        httpx.AsyncClient.post=original_post


if __name__=='__main__':main()
