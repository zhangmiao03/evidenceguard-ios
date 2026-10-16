"""Evaluate authorized, already-indexed recordings with private labelled queries.

The manifest's expected intervals are used ONLY for scoring, never sent to a
model. Does not import/re-index media, operate a device, or change its settings.
Use a database/media snapshot, not a second writer against the live service.
"""
import argparse, asyncio, json, os
from collections import Counter
from pathlib import Path
from dotenv import load_dotenv
from ..store import Store
from .service import VideoService
from .search import SearchInput


def validate(cases):
    ids=set(); groups={}; recordings={}
    for case in cases:
        if case['id'] in ids: raise ValueError('评测用例 ID 重复')
        ids.add(case['id'])
        if case['mode'] not in {'text','image','joint'} or case['split'] not in {'tuning','held_out'}:
            raise ValueError('用例需指定 text/image/joint 和 tuning/held_out')
        has_text=bool(case.get('text')); has_image=bool(case.get('image'))
        if (has_text,has_image)!={'text':(True,False),'image':(False,True),'joint':(True,True)}[case['mode']]:
            raise ValueError('查询模态与实际输入不一致')
        if not case.get('event_group'): raise ValueError('请提供事件分组，避免重叠窗口跨集合泄漏')
        groups.setdefault(case['event_group'],set()).add(case['split'])
        for expected in case['expected']:
            if not 0<=expected['start']<=expected['end']: raise ValueError('标注时间无效')
            if expected['kind'] not in {'appearance','action'}: raise ValueError('标注需区分外观和动作')
            recordings.setdefault(expected['recording_id'],set()).add(case['split'])
    if any(len(v)>1 for v in [*groups.values(),*recordings.values()]):
        raise ValueError('同一录像或事件不能同时进入调参与留出集合')


def overlap(hit, expected):
    return hit['recordingId']==expected['recording_id'] and hit['segmentStart']<=expected['end'] and hit['segmentEnd']>=expected['start']


def summarize(rows):
    report={}
    for split in ('tuning','held_out'):
        group=[r for r in rows if r['split']==split]
        by_mode={mode:sum(r['mode']==mode for r in group) for mode in ('text','image','joint')}
        totals=Counter();found=Counter()
        for row in group:
            totals.update(row['expectedByKind']);found.update(row['foundByKind'])
        report[split]=dict(queries=len(group),byMode=by_mode,
            recallAt10={kind:found[kind]/totals[kind] if totals[kind] else None for kind in ('appearance','action')},
            modelConfirmed=sum(r['matched'] for r in group),correctlyLocatedConfirmations=sum(r['correctlyLocated'] for r in group),
            negativeQueries=sum(r['negative'] for r in group),falseConfirmationsOnNegativeQueries=sum(r['falseConfirmation'] for r in group),
            failedQueries=sum(r['status'] in {'failed','interrupted','no_indexed_recordings','no_recordings'} for r in group),
            failedVerifications=sum(r['verificationFailed'] for r in group),uncertain=sum(r['uncertain'] for r in group),
            minimumQueryCountMet=all(n>=20 for n in by_mode.values()),
            acceptance='pending_manual_review_and_quality_thresholds')
    return report


async def evaluate(args):
    cases=json.loads(args.manifest.read_text(encoding='utf-8'))['cases'];validate(cases)
    if not args.database.is_file() or not args.media_root.is_dir(): raise ValueError('请使用已有录像库的数据库和媒体副本')
    store=Store(args.database);service=VideoService(store,args.media_root);rows=[]
    try:
        for case in cases:
            image_ref=None
            if case.get('image'):
                path=(args.manifest.parent/case['image']).resolve()
                if not path.is_relative_to(args.manifest.parent.resolve()): raise ValueError('参考图必须位于评测目录内')
                image_ref=service.retrieval.upload_image('evaluation',path.read_bytes())['id']
            # Explicit allowlist: expected labels, split and event_group never
            # enter SearchInput, prompts, embeddings or verifier requests.
            request=SearchInput(text=case.get('text'),image_ref=image_ref,camera_ids=case.get('camera_ids',[]),
                time_range=case.get('time_range',{'period':'all'}),timezone=case.get('timezone','Asia/Shanghai'),limit=10)
            result=service.retrieval.start(request,'evaluation');await service.retrieval.jobs[result['id']]
            result=service.retrieval.get(result['id'],'evaluation');hits=result['videos'];expected=case['expected']
            matched=[h for h in hits if h['verdict']=='matched']
            row=dict(id=case['id'],mode=case['mode'],split=case['split'],status=result['status'],
                expectedByKind=dict(Counter(e['kind'] for e in expected)),
                foundByKind=dict(Counter(e['kind'] for e in expected if any(overlap(h,e) for h in result.get('candidateWindows',hits)))),
                matched=len(matched),correctlyLocated=sum(any(h['recordingId']==e['recording_id'] and e['start']<=h['seekSeconds']<=e['end'] for e in expected) for h in matched),
                negative=not expected,falseConfirmation=not expected and bool(matched),
                verificationFailed=sum(h['verificationStatus']=='failed' for h in hits),uncertain=sum(h['verdict']=='uncertain' for h in hits),
                timings=result['timings'],searchId=result['id'],narrativeReview='pending')
            rows.append(row)
            args.output.write_text(json.dumps(dict(plannedQueries=len(cases),completedQueries=len(rows),complete=len(rows)==len(cases),cases=rows,summary=summarize(rows)),ensure_ascii=False,indent=2),encoding='utf-8')
    finally: await service.shutdown();store.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('manifest','database','media-root','output'): parser.add_argument('--'+flag,type=Path,required=True)
    args=parser.parse_args()
    if os.getenv('EG_ENV_FILE'): load_dotenv(os.environ['EG_ENV_FILE'],override=False)
    asyncio.run(evaluate(args))


if __name__=='__main__': main()
