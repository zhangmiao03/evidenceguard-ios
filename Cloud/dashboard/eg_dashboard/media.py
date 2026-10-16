"""Read-only, bounded media index projection; never publishes source media paths."""
import hashlib
import json
import math


def read_media(path, now, signature=None):
    from .collector import readonly, resource
    from .content import safe_record
    rows = []
    summary = {'status': 'connected', 'sampledAt': now, 'limitPerTable': 120,
               'currentSignature': signature, 'tables': {},
               'definition': 'Database snapshot; vector values are a preview, not model confidence. No media bytes or URLs.'}
    fields = {
        'recordings': {'id','cameraId','title','recordedAt','sourceType','createdAt','status','duration','segmentCount','indexedSegments','embeddingModel','embeddingSignature','error'},
        'sdk_episodes': {'id','cameraId','kind','status','revision','reason','review','reviewedEvidenceIds','attempts','updatedAt'},
        'visual_cache': {'status','review','cached','limitation'},
        'evidence': {'id','cameraId','skillId','capturedAt','sampledAt','receivedAt','observedAt','sourceType','reviewStatus','reason','visualReview','limitation','timestampMeaning'},
    }
    with readonly(path) as db:
        db.execute('BEGIN')
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table, allowed in fields.items():
            if table not in tables:
                summary['tables'][table] = {'available': False, 'total': None}
                continue
            total = db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            summary['tables'][table] = {'available': True, 'total': total, 'truncated': total > 120}
            columns = 'id,payload,status' if table == 'sdk_episodes' else 'id,payload'
            for row in db.execute(f'SELECT {columns} FROM {table} ORDER BY rowid DESC LIMIT 120'):
                try:
                    item = json.loads(row[1])
                    if not isinstance(item,dict): continue
                except (ValueError,TypeError): continue
                if table == 'evidence' and not (item.get('reviewStatus') or item.get('visualReview')): continue
                value = {k:v for k,v in item.items() if k in allowed}
                value['id'] = row[0]
                if table == 'sdk_episodes': value['status'] = row[2]
                if table == 'recordings':
                    value['signatureCompatible'] = item.get('embeddingSignature') == signature if signature else None
                value['snapshotOnly'] = True
                # Review providers return only these structured text fields.
                if 'review' in value:
                    value['review'] = review_projection(value['review'])
                if 'visualReview' in value:
                    value['visualReview'] = review_projection(value['visualReview'])
                rows.append(resource('media_'+table,safe_record(value),now))
        if 'video_segments' not in tables:
            summary['tables']['video_segments'] = {'available':False,'total':None}
        else:
            total = db.execute('SELECT COUNT(*) FROM video_segments').fetchone()[0]
            matching = db.execute('SELECT COUNT(*) FROM video_segments WHERE signature=?',(signature,)).fetchone()[0] if signature else None
            summary['tables']['video_segments'] = {'available':True,'total':total,'matchingSignature':matching,'truncated':total>120}
            invalid = 0
            for sid,rid,sig,payload,raw in db.execute('SELECT id,recording_id,signature,payload,CASE WHEN length(vector)<=65536 THEN vector ELSE NULL END FROM video_segments ORDER BY rowid DESC LIMIT 120'):
                try: item=json.loads(payload)
                except (ValueError,TypeError): item={}
                try: vector=json.loads(raw)
                except (ValueError,TypeError): vector=None
                valid=isinstance(vector,list) and bool(vector) and all(type(v) in (float,int) and math.isfinite(v) for v in vector)
                norm=math.hypot(*vector) if valid else None
                valid=valid and norm is not None and math.isfinite(norm) and norm>0
                if not valid: invalid+=1
                value={k:item[k] for k in ('cameraId','start','end') if isinstance(item,dict) and k in item}
                value.update(id=sid,recordingId=rid,signature=sig,
                             dimensions=len(vector) if isinstance(vector,list) else None,
                             norm=round(norm,8) if valid else None,
                             vectorPreview=vector[:16] if valid else [],
                             vectorHash=hashlib.sha256(raw.encode()).hexdigest() if raw else None,
                             status='valid' if valid else 'invalid',
                             normalized=abs(norm-1)<1e-5 if valid else False,
                             signatureCompatible=sig==signature if signature else None,
                             snapshotOnly=True)
                rows.append(resource('media_video_segments',value,now))
            summary['invalidVectorsInSample']=invalid
    return rows,summary


def review_projection(value):
    if not isinstance(value,dict):return None
    allowed={'visible','uncertainties','status','reason','cached','limitation','state','regionClear','identityClear','summary'}
    result={k:v for k,v in value.items() if k in allowed and isinstance(v,(str,bool,int,float))}
    if isinstance(value.get('review'),dict):result['review']=review_projection(value['review'])
    return result


def visual_traces(db):
    """Keep recent visual calls inspectable despite a burst of client polling.

    Read a bounded supplement of real rows, never recreate missing content.
    """
    traces=[r[0] for r in db.execute("""SELECT json_extract(payload,'$.traceId') FROM records
        WHERE json_extract(payload,'$.kind')='model'
        AND json_extract(payload,'$.name') IN ('image_review','frame_presence','video_verify','embedding')
        GROUP BY json_extract(payload,'$.traceId') ORDER BY MAX(at) DESC LIMIT 20""")]
    if not traces:return [],{'traces':0,'returned':0,'truncated':False,'traceLimit':20,'recordLimit':120,'byteLimit':1000000}
    placeholders=','.join('?' for _ in traces)
    values=[];size=0;cut=False
    for (raw,) in db.execute(f"SELECT payload FROM records WHERE json_extract(payload,'$.traceId') IN ({placeholders}) ORDER BY at DESC LIMIT 121",traces):
        if len(values)>=120 or size+len(raw.encode())>1000000:cut=True;break
        size+=len(raw.encode());values.append(json.loads(raw))
    return values,{'traces':len(traces),'returned':len(values),'truncated':cut,'traceLimit':20,'recordLimit':120,'byteLimit':1000000}
