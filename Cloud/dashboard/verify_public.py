"""Read public projections and verify original App authentication after deployment.

Does not call models or authenticated business operations. The one POST targets
the read-only Dashboard and must be rejected with 405.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
import httpx
from evidenceguard.ops import validate_bundle

with httpx.Client(timeout=12,trust_env=False) as client:
    base='http://47.131.21.137'
    checks={}
    for path,expected in [('/dashboard',200),('/dashboard/api/info',200),('/dashboard/api/snapshot?environment=invalid',422),('/dashboard/api/agent/runs',404)]:
        response=client.get(base+path);assert response.status_code==expected,(path,response.status_code)
        checks[path]=response.status_code
    assert client.head(base+'/dashboard').status_code==200
    assert client.post(base+'/dashboard/api/snapshot',json={}).status_code==405
    environments={}
    for label in ['demo','team','review']:
        response=client.get(base+'/dashboard/api/snapshot',params={'environment':label});response.raise_for_status()
        bundle=validate_bundle(response.json());coverage=bundle['coverage']
        assert coverage['observability']=='connected' and not coverage['stale']
        assert coverage['deployment']['processMatchesObserver']
        assert coverage['deployment']['diskVsRunning']==[]
        assert coverage['server']['memoryTotalBytes']>0
        environments[label]={'records':len(bundle['records']),'pythonDifferences':len(coverage['deployment']['diskVsRepository']),
            'observer':coverage['deployment']['observerRevision'],'liveProcesses':[s['state'] for s in coverage['server']['services']]}
        domain='https://'+label+'.47.131.21.137.sslip.io'
        assert client.get(domain+'/api/health').status_code==200
        assert client.get(domain+'/api/bootstrap').status_code==401
    print(json.dumps({'checks':checks,'writeRequest':405,'HEAD':200,'environments':environments,'appHealth':200,'appUnauthenticatedAPI':401}))
