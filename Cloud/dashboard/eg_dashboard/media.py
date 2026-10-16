"""Read-only, bounded media index projection; never publishes source media paths."""
import hashlib
import json
import math
import struct


def read_media(path, now, signature=None, assets=None, video_root=None):
    from .collector import readonly, resource
    from .content import safe_record
    rows = []
    summary = {'status': 'connected', 'sampledAt': now, 'limitPerTable': 120,
               'currentSignature': signature, 'tables': {},
               'definition': 'Database snapshot; referenced source media is copied to a bounded public cache. Similarity is not confidence.'}
    fields = {
        'recordings': {'id','cameraId','title','recordedAt','sourceType','createdAt','status','duration','segmentCount','indexedSegments','embeddingModel','embeddingSignature','error'},
        'sdk_episodes': {'id','cameraId','kind','status','revision','reason','review','reviewedEvidenceIds','attempts','updatedAt'},
        'visual_cache': {'status','review','cached','limitation'},
        'evidence': {'id','cameraId','skillId','capturedAt','sampledAt','receivedAt','observedAt','sourceType','reviewStatus','reason','visualReview','limitation','timestampMeaning'},
        'sdk_events': {'id','cameraId','episodeId','kind','hasVideo','createdAt','receivedAt','sourceType'},
    }
    with readonly(path) as db:
        db.execute('BEGIN')
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        def preview(item):
            from urllib.parse import urlsplit
            url=item.get('imageUrl')
            if not assets or 'media' not in tables or not isinstance(url,str) or not url.startswith('/api/media/'):return None
            key=urlsplit(url).path.removeprefix('/api/media/')
            row=db.execute('SELECT bytes,mime FROM media WHERE id=? AND length(bytes)<=8000000',(key,)).fetchone()
            return assets.add(row[0],row[1],provenance='stored_source') if row else None
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
                value = {k:v for k,v in item.items() if k in allowed}
                value['id'] = row[0]
                if table == 'sdk_episodes': value['status'] = row[2]
                if table == 'recordings':
                    value['signatureCompatible'] = item.get('embeddingSignature') == signature if signature else None
                    if assets and video_root:
                        from pathlib import Path
                        import re
                        rid=str(row[0]);root=Path(video_root).resolve()
                        if re.fullmatch(r'video-[a-f0-9]{16}',rid):
                            file=root/rid/'playback.mp4'
                            if file.is_file() and not file.is_symlink() and file.resolve().is_relative_to(root) and file.stat().st_size<=32000000:
                                value['media']=[assets.add(file.read_bytes(),'video/mp4',provenance='stored_recording')]
                if table in {'evidence','sdk_events'}:
                    p=preview(item)
                    if p:value['media']=[p]
                if table == 'sdk_episodes' and 'sdk_events' in tables:
                    value['media']=[]
                    for (payload,) in db.execute("SELECT payload FROM sdk_events WHERE json_extract(payload,'$.episodeId')=? ORDER BY rowid LIMIT 6",(row[0],)):
                        try:p=preview(json.loads(payload))
                        except (ValueError,TypeError):p=None
                        if p:value['media'].append(p)
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
        # v2 is a separate index. Project only atomically published vectors and
        # metadata; never export private query images, local paths or jobs.
        if {'retrieval_embeddings','retrieval_units','retrieval_clips','retrieval_recordings'} <= tables:
            join=''' FROM retrieval_embeddings e JOIN retrieval_units u ON u.id=e.unit_id AND u.signature=e.signature
                JOIN retrieval_clips c ON c.id=e.clip_id AND c.signature=e.signature
                JOIN retrieval_recordings r ON r.id=c.recording_id AND r.active_signature=c.signature'''
            total=db.execute('SELECT count(*)'+join).fetchone()[0]
            matching=db.execute('SELECT count(*)'+join+' WHERE e.signature=?',(signature,)).fetchone()[0] if signature else None
            summary['tables']['retrieval_embeddings']={'available':True,'total':total,'matchingSignature':matching,'truncated':total>120}
            for clip_id,rid,sig,kind,offset,start,end,dimensions,raw in db.execute(
                'SELECT c.id,r.id,e.signature,e.kind,e.offset_ms,c.start,c.end,u.dimensions,CASE WHEN length(u.vector)=4096 THEN u.vector ELSE NULL END'+join+' ORDER BY e.rowid DESC LIMIT 120'):
                vector=struct.unpack('<1024f',raw) if raw is not None and dimensions==1024 else ()
                norm=math.hypot(*vector) if vector and all(math.isfinite(x) for x in vector) else None
                valid=norm is not None and math.isfinite(norm) and norm>0
                value=dict(id=f'{clip_id}-{kind}-{offset}',clipId=clip_id,recordingId=rid,signature=sig,kind=kind,
                    frameOffsetSeconds=offset/1000 if kind=='frame' else None,start=start,end=end,dimensions=dimensions,
                    norm=round(norm,8) if valid else None,normalized=abs(norm-1)<1e-5 if valid else False,
                    vectorPreview=list(vector[:16]) if valid else [],vectorHash=hashlib.sha256(raw).hexdigest() if raw else None,
                    signatureCompatible=sig==signature if signature else None,status='valid' if valid else 'invalid',snapshotOnly=True,indexVersion=2)
                rows.append(resource('media_video_segments',value,now))
        else: summary['tables']['retrieval_embeddings']={'available':False,'total':None}
    return rows,summary


def review_projection(value):
    if not isinstance(value,dict):return None
    allowed={'visible','uncertainties','status','reason','cached','limitation','state','regionClear','identityClear','summary'}
    result={k:v for k,v in value.items() if k in allowed and isinstance(v,(str,bool,int,float))}
    if isinstance(value.get('review'),dict):result['review']=review_projection(value['review'])
    return result


def visual_traces(db):
    """Keep recent Agent/model tasks inspectable despite client polling.

    Read a bounded supplement of real rows, never recreate missing content.
    """
    source = 'critical_records' if db.execute("SELECT 1 FROM sqlite_master WHERE name='critical_records'").fetchone() else 'records'
    traces=[r[0] for r in db.execute(f"""SELECT json_extract(payload,'$.traceId') FROM {source}
        WHERE json_extract(payload,'$.kind')='model'
        OR json_extract(payload,'$.name') IN ('agent.result','vector.search')
        OR (json_extract(payload,'$.kind')='prompt' AND json_array_length(payload,'$.data.inputMedia')>0)
        GROUP BY json_extract(payload,'$.traceId') ORDER BY MAX(at) DESC LIMIT 20""")]
    if not traces:return [],{'traces':0,'returned':0,'truncated':False,'traceLimit':20,'recordLimit':240,'byteLimit':2500000}
    placeholders=','.join('?' for _ in traces)
    values=[];size=0;cut=False
    for (raw,) in db.execute(f"SELECT payload FROM {source} WHERE json_extract(payload,'$.traceId') IN ({placeholders}) ORDER BY at DESC LIMIT 241",traces):
        if len(values)>=240:cut=True;break
        # A large prompt must not hide all other tasks and final receipts.
        if size+len(raw.encode())>2500000:cut=True;continue
        size+=len(raw.encode());values.append(json.loads(raw))
    return values,{'traces':len(traces),'returned':len(values),'truncated':cut,'traceLimit':20,'recordLimit':240,'byteLimit':2500000}


def is_critical(row):
    name=row.get('name','')
    return row.get('kind') in {'model','prompt'} or name.startswith(('agent.','tool.','codex.','context.','model.')) or name in {'camera_completed','camera_failed','vector.search'}
