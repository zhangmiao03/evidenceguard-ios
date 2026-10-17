"""Full record inventory, separate from the bounded recent trace snapshot.

Only the privileged collector opens business files. HTTP reads a secret-filtered
SQLite projection; no private reference-image content, source paths or keys.
"""
import base64
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import time
from . import content


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def numeric(value):
    return value if type(value) in (int, float) and math.isfinite(value) else 0


def table_names(db):
    return {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def load_secrets(environment, pid=None):
    """Fail closed on body publication if the explicit redaction source is absent."""
    paths = environment.get('secretFiles', [])
    if not paths: return None
    from dotenv import dotenv_values
    values = set()
    try:
        for path in paths:
            if not Path(path).is_file(): return None
            for key, value in dotenv_values(path).items():
                if value and len(value) >= 8 and content.ENV_SECRET.search(key): values.add(value)
        # Effective process overrides can differ from cloud.env. Read only the
        # already-verified app PID, keep secret values in memory for redaction.
        if pid:
            for pair in Path(f'/proc/{int(pid)}/environ').read_bytes().split(b'\0'):
                key, sep, raw = pair.partition(b'=')
                if sep and content.ENV_SECRET.search(key.decode(errors='ignore')) and len(raw)>=8:
                    values.add(raw.decode(errors='replace'))
    except (OSError, ValueError): return None
    return sorted(values, key=len, reverse=True)


def display_check(run, receipts):
    own = [r for r in receipts if r.get('traceId') == run.get('id')]
    own.sort(key=lambda r: r.get('at', 0), reverse=True)
    latest = next((r for r in own if r.get('data', {}).get('backendTextHash')), own[0] if own else None)
    if latest is None: return {'status':'not_reported'}
    data = latest.get('data', {})
    reported = data.get('backendTextHash')
    result = {k:data[k] for k in ('backendTextHash','displayTextHash','presentationVersion','appVersion','hashAlgorithm') if k in data}
    result.update(at=latest['at'], platform=latest.get('platform'), clientReported=True,
        status='legacy_receipt' if not reported else 'backend_match' if reported == hashlib.sha256((run.get('text') or '').encode('utf-8')).hexdigest() else 'backend_mismatch')
    return result


def project(database, observations, output, environment, now, assets, *, secrets=None, capture=False):
    from .collector import readonly, public_record
    target = Path(output)/(environment+'-archive.sqlite3')
    out = sqlite3.connect(target, timeout=2)
    out.executescript('''
        CREATE TABLE IF NOT EXISTS entries(section TEXT,id TEXT,at REAL,platform TEXT,source TEXT,device TEXT,payload TEXT,generation REAL,PRIMARY KEY(section,id));
        CREATE INDEX IF NOT EXISTS entries_page ON entries(section,at DESC,id DESC);
        CREATE TABLE IF NOT EXISTS steps(id TEXT PRIMARY KEY,trace_id TEXT,at REAL,payload TEXT,generation REAL);
        CREATE INDEX IF NOT EXISTS steps_trace ON steps(trace_id,at);
        CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,payload TEXT);
    ''')
    receipts = []; traces = {}; retained_ids = set(); input_traces = {}
    summary = {'sampledAt':now,'images':{'total':0,'uniqueContents':0,'previewable':0,'bytes':0,'sources':{}},
               'replies':{'total':0,'nonempty':0,'withSteps':0,'withDisplayReceipt':0,'hashMatched':0},
               'retention':{'status':'unavailable'},'bodyCapture':capture and secrets is not None}
    try:
        with out:
            # Archive existing real critical steps, not synthetic history. A
            # previously pruned prompt cannot be reconstructed from a reply.
            try:
                with readonly(observations) as obs:
                    obs.execute('BEGIN')
                    tables = table_names(obs)
                    source = 'critical_records' if 'critical_records' in tables else 'records'
                    from_sql = f'SELECT payload FROM {source} ORDER BY at'
                    for raw, in obs.execute(from_sql):
                        try: value = json.loads(raw)
                        except (ValueError, TypeError): continue
                        from .media import is_critical
                        if not is_critical(value): continue
                        if value.get('name') == 'agent.displayed': receipts.append(value)
                        row = public_record(value)
                        # Collector applies actual configured secret values to
                        # bodies once more, including migrated historical steps.
                        row, _ = content.clean(row, budget=content.MAX_TEXT*2, known_secrets=secrets or [])
                        data = row.get('data', {})
                        for key in ('inputMedia',):
                            if isinstance(data.get(key), list): data[key] = [assets.reference(m) for m in data[key][:6]]
                        rid, trace = row['id'], row['traceId']
                        retained_ids.add(rid); traces[trace] = traces.get(trace, 0)+1
                        for media in data.get('inputMedia', []):
                            if isinstance(media,dict) and media.get('assetId'):
                                input_traces.setdefault(media['assetId'],set()).add(trace)
                        out.execute('INSERT INTO steps VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,generation=excluded.generation',
                                    (rid,trace,numeric(row['at']),encode(row),now))
                    if 'critical_records' in tables:
                        count, size, oldest = obs.execute('SELECT count(*),coalesce(sum(bytes),0),min(at) FROM critical_records').fetchone()
                        policy = obs.execute("SELECT value FROM metadata WHERE key='criticalPolicy'").fetchone()
                        evicted = obs.execute("SELECT value FROM metadata WHERE key='criticalEvicted'").fetchone()
                        summary['retention'] = {'status':'separate','records':count,'bytes':size,'oldestAt':oldest,
                            'evictedRecords':int(evicted[0]) if evicted else 0, **(json.loads(policy[0]) if policy else {})}
                    else: summary['retention'] = {'status':'legacy_window','records':len(retained_ids)}
            except (OSError, sqlite3.Error):
                # Business inventory still works; never report old receipts as fresh.
                traces = {}; receipts = []
            out.execute('DELETE FROM steps WHERE generation<>?', (now,))
            digests = set()
            with readonly(database) as db:
                db.execute('BEGIN')
                tables = table_names(db)
                if 'media' in tables:
                    for mid, raw, mime, payload in db.execute('SELECT id,bytes,mime,payload FROM media ORDER BY rowid DESC'):
                        item = json.loads(payload); frame = item.get('frame', {})
                        digest = hashlib.sha256(raw).hexdigest(); digests.add(digest)
                        preview = assets.add(raw,mime,provenance='stored_frame')
                        source = frame.get('source_type', 'unknown')
                        at = numeric(frame.get('received_at')) or numeric(frame.get('sampled_at')) or numeric(frame.get('captured_at'))
                        value = dict(id=mid,cameraId=frame.get('device_id'),sourceType=source,status='stored',mime=mime,
                            bytes=len(raw),sha256=digest,receivedAt=frame.get('received_at'),sampledAt=frame.get('sampled_at'),
                            capturedAt=frame.get('captured_at'),media=[preview] if preview else [],
                            previewStatus='available' if preview else 'cache_budget_or_unsupported',
                            modelInputTraces=[{'id':t,'retainedSteps':traces.get(t,0)} for t in sorted(input_traces.get(digest,()))],
                            timestampMeaning='server_received',recordSource='business_database',snapshotOnly=True)
                        value, _ = content.clean(value, known_secrets=secrets or [])
                        platform = 'ios' if source.endswith('_ios') else 'web' if source.endswith('_web') else 'backend'
                        out.execute('INSERT OR REPLACE INTO entries VALUES (?,?,?,?,?,?,?,?)',
                            ('images',mid,at,platform,'snapshot',frame.get('device_id') or '',encode(value),now))
                        s = summary['images']; s['total']+=1; s['bytes']+=len(raw); s['previewable']+=int(bool(preview))
                        s['sources'][source]=s['sources'].get(source,0)+1
                summary['images']['uniqueContents'] = len(digests)
                if 'runs' in tables:
                    for rid, raw in db.execute('SELECT id,payload FROM runs ORDER BY rowid DESC'):
                        run = json.loads(raw); run['id'] = rid
                        text = run.get('text') or ''; private = bool(run.get('referenceImageId') or run.get('privateContent') or run.get('endpointAnalyses'))
                        allow = capture and secrets is not None and not private
                        answer, clean = content.clean(text, known_secrets=secrets or []) if allow else (None, {})
                        verification = display_check(run, receipts)
                        value = dict(id=rid,status=run.get('status','unknown'),executionMode=run.get('executionMode'),
                            createdAt=run.get('createdAt'),completedAt=run.get('completedAt'),cameraId=run.get('cameraId'),
                            platform=run.get('clientPlatform') or 'unknown',answer=answer,hasReply=bool(text),
                            replyCharacters=len(text),backendTextHash=hashlib.sha256(text.encode('utf-8')).hexdigest() if text else None,
                            bodyStatus='private_content' if private else 'available' if allow else 'capture_disabled',
                            capture=clean,displayVerification=verification,retainedSteps=traces.get(rid,0),
                            historyStatus='retained_steps_only' if traces.get(rid) else 'steps_not_retained_or_not_captured',
                            recordSource='business_database',snapshotOnly=True)
                        at = numeric(run.get('createdAt'))
                        out.execute('INSERT OR REPLACE INTO entries VALUES (?,?,?,?,?,?,?,?)',
                            ('replies',rid,at,run.get('clientPlatform') or 'backend','snapshot',run.get('cameraId') or '',encode(value),now))
                        s=summary['replies'];s['total']+=1;s['nonempty']+=int(bool(text));s['withSteps']+=int(bool(traces.get(rid)))
                        s['withDisplayReceipt']+=int(verification['status']!='not_reported');s['hashMatched']+=int(verification['status']=='backend_match')
            out.execute('DELETE FROM entries WHERE generation<>?', (now,))
            out.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)', ('summary',encode(summary)))
        target.chmod(0o644)
    finally: out.close()
    return summary


def filters(section, *, query='', platform='', source='', device='', since=0):
    clauses=['section=?']; values=[section]
    for key, value in [('platform',platform),('source',source),('device',device)]:
        if value: clauses.append(key+'=?'); values.append(value)
    if since: clauses.append('at>=?');values.append(since)
    if query:
        clauses.append("payload LIKE ? ESCAPE '\\'")
        values.append('%'+query.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%')
    return ' AND '.join(clauses), values


def cursor_for(row):
    return base64.urlsafe_b64encode(encode([row[0],row[1]]).encode()).decode().rstrip('=')


def read_page(path, section, *, limit=24, cursor='', **scope):
    from .collector import readonly
    where, values = filters(section, **scope)
    with readonly(path) as db:
        db.execute('BEGIN')
        summary = json.loads(db.execute("SELECT payload FROM metadata WHERE key='summary'").fetchone()[0])
        total = db.execute('SELECT count(*) FROM entries WHERE '+where,values).fetchone()[0]
        if cursor:
            try:
                at, rid = json.loads(base64.urlsafe_b64decode(cursor+'='*(-len(cursor)%4)))
                if not isinstance(rid,str) or not isinstance(at,(float,int)) or not math.isfinite(at): raise ValueError()
            except Exception: raise ValueError('Invalid page cursor')
            where+=' AND (at<? OR (at=? AND id<?))';values.extend([at,at,rid])
        rows=db.execute('SELECT at,id,payload FROM entries WHERE '+where+' ORDER BY at DESC,id DESC LIMIT ?',[*values,limit+1]).fetchall()
        return {'section':section,'items':[json.loads(r[2]) for r in rows[:limit]],'total':total,'limit':limit,
            'nextCursor':cursor_for(rows[limit-1]) if len(rows)>limit else None,'summary':summary,
            'sampledAt':summary['sampledAt'],'stale':time.time()-summary['sampledAt']>20}
