"""Repeatable, labelled video checks. Labels never enter model requests."""
from __future__ import annotations
import argparse, asyncio, hashlib, json, os, statistics, time
from pathlib import Path
from dotenv import load_dotenv
from .providers import LiteVideoProvider, ArkVideoEmbedding, ProviderError
from .service import probe


def assess(result, expected):
    verdict=result['verdict']
    window=expected.get('eventWindow')
    at=result.get('eventTime')
    time_error=None if not window or at is None else max(window[0]-at,0,at-window[1])
    return dict(verdictCorrect=verdict==expected['verdict'],
        falseConfirmation=verdict=='matched' and expected['verdict']!='matched',
        missedPositive=expected['verdict']=='matched' and verdict!='matched',
        timeOutsideWindowSeconds=time_error,
        structuredPass=verdict==expected['verdict'] and (not window or time_error==0),
        narrativeReview='pending: a correct label/timestamp does not prove the description is true')


async def evaluate(manifest, root, output, repeats=3):
    spec=json.loads(manifest.read_text()); provider=LiteVideoProvider(); embedding=ArkVideoEmbedding()
    report=dict(version=1,startedAt=time.time(),model=provider.model,temperature=0,repeats=repeats,
        manifestSHA256=hashlib.sha256(manifest.read_bytes()).hexdigest(),cases=[],missingCoverage=spec.get('missingCoverage',[]))
    gate=asyncio.Semaphore(2)
    def save():
        output.parent.mkdir(parents=True,exist_ok=True)
        temp=output.with_suffix('.tmp'); temp.write_text(json.dumps(report,ensure_ascii=False,indent=2)); temp.replace(output)
    for case in spec['cases']:
        path=root/case['file']
        row={k:v for k,v in case.items() if k!='file'} | {'trials':[]}; report['cases'].append(row)
        if not path.is_file(): row['missing']=True; save(); continue
        row['sha256']=hashlib.sha256(path.read_bytes()).hexdigest(); duration=await probe(path)
        async def trial(n):
            async with gate:
                began=time.monotonic()
                try:
                    result=await provider.verify(path,case['query'],duration)
                    value=dict(repeat=n,result=result,assessment=assess(result,case['expected']))
                except Exception as error:
                    value=dict(repeat=n,error=type(error).__name__,errorDetail=str(error) if isinstance(error,(ProviderError,ValueError)) else '请求未完成',errorCode=getattr(error,'code',None),diagnostics=getattr(error,'diagnostics',[]),assessment={'structuredPass':False})
                value['latencySeconds']=round(time.monotonic()-began,3); row['trials'].append(value); save()
        await asyncio.gather(*(trial(n+1) for n in range(repeats)))
        row['trials'].sort(key=lambda x:x['repeat'])
        row['verdictAgreement']=len({t.get('result',{}).get('verdict','error') for t in row['trials']})==1
    # Test query→video ranking separately, using no filename, source label or gold answer in inputs.
    if embedding.ready and spec.get('retrieval'):
        corpus={c['file'] for c in spec['cases'] if (root/c['file']).is_file()}
        vectors={name:await embedding.embed(video=root/name) for name in sorted(corpus)}
        report['retrieval']=[]
        for check in spec['retrieval']:
            began=time.monotonic(); vector=await embedding.embed(text=check['query'])
            ranked=sorted(((sum(a*b for a,b in zip(vector,v)),name) for name,v in vectors.items()),reverse=True)
            report['retrieval'].append(dict(query=check['query'],ranking=[{'file':name,'similarity':score} for score,name in ranked],
                top1Correct=bool(ranked and ranked[0][1]==check['expectedTop1']),latencySeconds=round(time.monotonic()-began,3)))
            save()
    trials=[t for c in report['cases'] for t in c['trials']]
    ok=[t for t in trials if 'result' in t]
    report['metrics']=dict(trials=len(trials),invalidOrFailedResults=len(trials)-len(ok),validResults=len(ok),
        structuredPasses=sum(t['assessment']['structuredPass'] for t in trials),
        falseConfirmations=sum(t['assessment'].get('falseConfirmation',False) for t in trials),
        missedPositives=sum(t['assessment'].get('missedPositive',False) for t in trials),
        medianLatencySeconds=statistics.median([t['latencySeconds'] for t in trials]) if trials else None,
        maxLatencySeconds=max((t['latencySeconds'] for t in trials),default=None))
    report['finishedAt']=time.time(); report['automaticGuardAcceptance']='NOT_EVALUATED: missing continuous footage and independent narrative review'
    save(); return report


async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--manifest',type=Path,required=True); parser.add_argument('--video-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True); parser.add_argument('--repeats',type=int,default=3)
    args=parser.parse_args()
    if not 1<=args.repeats<=10: parser.error('repeats must be 1–10')
    if os.getenv('EG_ENV_FILE'): load_dotenv(os.environ['EG_ENV_FILE'])
    result=await evaluate(args.manifest,args.video_root,args.output,args.repeats)
    print(json.dumps(result['metrics'],ensure_ascii=False))

if __name__=='__main__': asyncio.run(main())
