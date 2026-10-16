"""Project only deliberate public test cases; never scan private search jobs."""
import hashlib
import json
from pathlib import Path

from .content import safe_record
from .media_assets import ID, MIMES, valid_bytes


def pick(value, fields):
    return {key:value[key] for key in fields.split() if isinstance(value,dict) and key in value}


def project(output, label, assets, records, state, environment, now):
    from .collector import readonly, resource
    folder=Path(output)/'briefing'/label
    file=folder/'manifest.json'
    if not file.is_file() or file.is_symlink() or file.stat().st_size>1_000_000:return []
    case=json.loads(file.read_text(encoding='utf8'))
    if case.get('schema')!='evidenceguard.briefing/v1':return []
    source=case.get('source',{})
    recording=next((r['data'] for r in records if r['name']=='media_recordings' and r['data'].get('id')==source.get('recordingId')),None)
    # Revoked/deleted/replaced source disappears along with its public case.
    if not recording or not any(m and m.get('assetId')==source.get('assetId') for m in recording.get('media',[])):return []
    source=pick(source,'recordingId assetId duration sourceType')|{'title':recording.get('title'),'media':recording.get('media',[])}
    def media(items, provenance='public_recording_replay'):
        results=[]
        for index,item in enumerate(items[:8] if isinstance(items,list) else []):
            if not isinstance(item,dict) or not ID.fullmatch(str(item.get('assetId',''))) or item.get('mime') not in {'image/png','image/jpeg'}:continue
            path=folder/(item['assetId']+'.'+MIMES[item['mime']])
            if path.is_symlink() or not path.is_file() or path.stat().st_size>8_000_000:continue
            raw=path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=item['assetId'] or not valid_bytes(raw,item['mime']):continue
            value=assets.add(raw,item['mime'],label=item.get('label',''),position=str(index),provenance=provenance)
            if value:results.append(value)
        return results
    at=case.get('createdAt',now)
    rows=[]
    processing=pick(case.get('processing'),'mode sampleOffsets intervalMs liveGateApplied controlEligible latencyMs depth flow')
    # Diagnostics are schema-limited; no arbitrary worker output/paths survive.
    processing['depth']=pick(processing.get('depth'),'status model sha256 normalization metricDistance code')
    processing['flow']=pick(processing.get('flow'),'status code quality consistentFraction geometricInliers denseSparseDisagreementPx backgroundTranslationCandidate units limitation')
    processed_at=case.get('processing',{}).get('createdAt',at)
    processing.update(id=case.get('id'),source=source,createdAt=processed_at,media=media(case.get('processing',{}).get('media',[])))
    rows.append(resource('media_processing_case',safe_record(processing),processed_at))
    for item in case.get('searches',[])[:4]:
        value=pick(item,'id text queryType status createdAt reason timings metrics candidateCount verifiedCount querySignature indexSignature indexChanged embeddingModel verificationModel')
        value['referenceMedia']=media(item.get('referenceMedia',[]),'public_query_input')
        value['videos']=[]
        for video in item.get('videos',[])[:10]:
            if video.get('recordingId')!=source['recordingId']:continue
            v=pick(video,'id recordingId title segmentStart segmentEnd seekSeconds verificationStatus verdict summary limitation events rank ranking verifiedBy timestampEstimate')
            value['videos'].append(v)
        value.update(source=source,publication='explicit_public_test',createdAt=item.get('createdAt',at))
        value['signatureCompatible']=recording.get('embeddingSignature')==value.get('indexSignature')
        rows.append(resource('media_retrieval_case',safe_record(value),value['createdAt']))
    status=dict(id='local-vision',verifiedAt=at,sameProcess=case.get('servicePid')==state.get('pid'),
                configuration=pick(case.get('localVision'),'enabled ready depthReady flowReady depthModel flowAlgorithm frameIntervalLimitMs version maxParallel execution metricDistance decoderProofGenerated'),
                guardRunCoverage='not_recorded_by_deployed_observer')
    with readonly(environment['database']) as db:
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for name in ('endpoint_analyses','visual_controls'):
            status[name+'Count']=db.execute('SELECT count(*) FROM '+name).fetchone()[0] if name in tables else None
        if 'endpoint_analyses' in tables:
            status['endpointDiagnostics']=[]
            for raw, in db.execute('SELECT payload FROM endpoint_analyses ORDER BY rowid DESC LIMIT 8'):
                try:item=json.loads(raw)
                except (ValueError,TypeError):continue
                if not isinstance(item,dict):continue
                aux=item.get('auxiliary') or {}
                status['endpointDiagnostics'].append(pick(item,'status condition model createdAt latencyMs')|{
                    'depth':pick(aux.get('depth'),'status model code'),'flow':pick(aux.get('flow'),'status code quality intervalMs')})
    rows.append(resource('vision_processing_status',safe_record(status),now))
    return rows
