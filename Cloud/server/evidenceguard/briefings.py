"""Subscribed home reports: wall-clock scheduling and evidence-owned wording.

The model may rank existing facts, but cannot turn missing telemetry into safety,
invent identity, or decide whether a subscribed report is worth delivering.
"""
from __future__ import annotations

from collections import Counter
import asyncio
from datetime import datetime, time as clock_time, timedelta
import json
import re
from zoneinfo import ZoneInfo

from .camera.sources import REAL_SOURCES

SLOTS = ('morning', 'evening')
LABELS = {'morning': '早安报告', 'evening': '晚间报告'}
REPORT_GRACE_SECONDS = 2 * 3600
EVENT_LABELS = {'human': '有人', 'ring': '门铃响起', 'package_put': '包裹放下',
                'package_take': '包裹取走', 'motion': '移动', 'vehicle': '车辆', 'pet': '宠物'}


def display_name(value, fallback):
    # Names are untrusted tool data. Long or punctuated strings stay out of
    # the assistant's prose; the source record remains available for inspection.
    return '“'+value+'”' if re.fullmatch(r'[\w \-]{1,24}', value) else fallback


def normalize_preferences(raw):
    """Migrate the old daily opt-in to ONE evening slot, never opt into morning."""
    value = dict(raw)
    if 'morningReport' not in value and 'eveningReport' not in value:
        value.update(morningReport=False, eveningReport=value.get('dailySummary', False),
                     eveningHour=value.get('summaryHour', 18))
    value.setdefault('morningReport', False)
    value.setdefault('eveningReport', False)
    value.setdefault('morningHour', 8)
    value.setdefault('eveningHour', 20)
    value['dailySummary'] = value['morningReport'] or value['eveningReport']
    value['summaryHour'] = value['eveningHour'] if value['eveningReport'] else value['morningHour'] if value['morningReport'] else value.get('summaryHour', 18)
    return value


def schedule_signature(p):
    return {k: p[k] for k in ('timezone', 'morningReport', 'eveningReport', 'morningHour', 'eveningHour')}


def due_report(p, now):
    """Catch up only within two hours of the slot. DST folds deliver once per local day.

    A nonexistent spring-forward wall time resolves to the next valid instant.
    Intervals are adjacent in UTC and are not assumed to be exactly 12/24 hours.
    """
    zone = ZoneInfo(p['timezone'])
    today = datetime.fromtimestamp(now, zone).date()
    candidates = []
    for offset in (-2, -1, 0, 1, 2):
        day = today + timedelta(days=offset)
        for slot in SLOTS:
            if p[slot+'Report']:
                at = datetime.combine(day, clock_time(p[slot+'Hour']), zone).timestamp()
                candidates.append((at, slot, day.isoformat()))
    candidates.sort()
    past = [x for x in candidates if x[0] <= now]
    future = [x for x in candidates if x[0] > now]
    if len(past) < 2 or not future:
        return None
    end, slot, date = past[-1]
    if now >= end + REPORT_GRACE_SECONDS:
        return None
    return dict(slot=slot, localDate=date, timezone=p['timezone'], startAt=past[-2][0],
                endAt=end, expiresAt=min(future[0][0], end + REPORT_GRACE_SECONDS), schedule=schedule_signature(p))


def _rows(store, table):
    # Call sites use a fixed internal table name, never user/model input.
    if not store.db.execute('SELECT 1 FROM sqlite_master WHERE type=? AND name=?', ('table', table)).fetchone():
        return []
    return [json.loads(r[0]) for r in store.db.execute(f'SELECT payload FROM {table}')]


def facts(store, report, now):
    """Read actual persisted sources; no capture, SDK call, or fixture fallback."""
    start, end = report['startAt'], report['endAt']
    with store.lock:
        devices = {d['id']: d for table in ('sdk_devices', 'live_devices') for d in _rows(store, table)}
        ids = set(devices)
        # Aggregate in SQLite instead of loading/truncating a household's history.
        counts, last_by_camera = Counter(), {}
        if store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sdk_events'").fetchone():
            for camera, kind, count in store.db.execute("""SELECT camera,json_extract(payload,'$.metadata.detectionType'),COUNT(*) FROM sdk_events
                WHERE json_extract(payload,'$.metadata.startMs')>=? AND json_extract(payload,'$.metadata.startMs')<? AND received<=?
                GROUP BY camera,json_extract(payload,'$.metadata.detectionType')""", (start*1000,end*1000,now)):
                if camera in ids: counts[EVENT_LABELS.get(kind, '其他检测')] += count
            for camera, last in store.db.execute("""SELECT camera,MAX(json_extract(payload,'$.metadata.startMs'))/1000.0 FROM sdk_events
                WHERE json_extract(payload,'$.metadata.startMs')<? AND received<=? GROUP BY camera""", (end*1000,now)):
                if camera in ids: last_by_camera[camera] = last
        placeholders = ','.join('?' for _ in REAL_SOURCES)
        sample_count = 0
        for camera, source, last, count in store.db.execute(f"""SELECT json_extract(payload,'$.cameraId'),json_extract(payload,'$.sourceType'),
                MAX(json_extract(payload,'$.capturedAt')),SUM(CASE WHEN json_extract(payload,'$.capturedAt')>=? THEN 1 ELSE 0 END)
                FROM evidence WHERE json_extract(payload,'$.capturedAt')<? AND json_extract(payload,'$.sourceType') IN ({placeholders})
                GROUP BY json_extract(payload,'$.cameraId'),json_extract(payload,'$.sourceType')""", (start,end,*REAL_SOURCES)):
            if camera in ids:
                last_by_camera[camera] = max(last_by_camera.get(camera, 0), last)
                if source != 'official_sdk': sample_count += count
        skills = [s for s in store.skills() if s.get('devices') and set(s['devices']) <= ids and not s.get('replay')]
        watches = {w['cameraId']: w for w in _rows(store, 'camera_watches')}
        pictures = [json.loads(row[0]) for row in store.db.execute(f"""SELECT payload FROM evidence
            WHERE json_extract(payload,'$.capturedAt')>=? AND json_extract(payload,'$.capturedAt')<?
            AND json_extract(payload,'$.sourceType') IN ({placeholders})
            AND json_extract(payload,'$.mediaStatus')='saved'
            ORDER BY captured_at DESC LIMIT 30""", (start,end,*REAL_SOURCES))]

    sources = [dict(id='report:scope', type='report_scope', title=LABELS[report['slot']],
                    startAt=start, endAt=end, timezone=report['timezone'], observedAt=now,
                    deviceCount=len(ids), eventCount=sum(counts.values()), sampleCount=sample_count,
                    eventTypes=dict(counts), continuousCoverage=False,
                    limitation='当前为前台中继的离散记录；未收到事件不能证明没有事件或家里安全。')]
    for camera, device in sorted(devices.items()):
        last = last_by_camera.get(camera)
        watch = watches.get(camera, {})
        sources.append(dict(id='report:device:'+camera, type='report_device', cameraId=camera,
                            name=str(device.get('name') or '摄像头')[:60], observedAt=last,
                            hasPeriodData=last is not None and last >= start,
                            lastRecordAt=last, connection='unknown', continuousCoverage=False,
                            failedSampling=bool(watch.get('enabled') and start <= watch.get('lastAttemptAt', 0) <= now
                                                and watch.get('status') not in {'completed', 'waiting', 'disabled'}),
                            limitation='最近记录时间不是在线心跳；无新记录不等于设备离线。'))
    for skill in sorted(skills, key=lambda s: s['id']):
        if skill.get('alert')=='open' or (skill['status']=='active' and skill['result']=='unknown'):
            sources.append(dict(id='skill:'+skill['id'], type='report_task', skillId=skill['id'],
                                name=skill['name'][:60], status=skill['status'], result=skill['result'],
                                alert=skill.get('alert'), revision=skill['revision'], observedAt=now,
                                limitation='当前已保存任务状态；不证明本报告时段全程覆盖或人员身份。'))
    # At most three saved pictures, with different cameras represented first.
    # No SDK capture or camera control is started by a report.
    chosen, seen = [], set()
    for item in pictures:
        camera = item.get('cameraId')
        if camera not in ids or camera in seen or not re.fullmatch(r'/api/media/[a-f0-9]{64}',item.get('imageUrl') or ''): continue
        seen.add(camera); chosen.append(item)
        if len(chosen) == 3: break
    for item in pictures:
        if len(chosen) == 3: break
        if item in chosen or item.get('cameraId') not in ids or not re.fullmatch(r'/api/media/[a-f0-9]{64}',item.get('imageUrl') or ''): continue
        chosen.append(item)
    for item in chosen:
        sources.append(dict(id='report:picture:'+item['id'],type='report_picture',evidenceId=item['id'],
                            cameraId=item['cameraId'],observedAt=item['capturedAt'],imageUrl=item['imageUrl'],
                            sourceType=item['sourceType'],limitation='这张已保存画面中的可见内容，不代表全程情况。'))
    return sources


async def review_pictures(sources, visual, report):
    """Read a bounded set of saved images under the existing visual budget."""
    values = [dict(s) for s in sources]
    if visual is None: return values
    for source in values:
        if source['type'] != 'report_picture': continue
        try:
            async with asyncio.timeout(18):
                source['visualReview'] = await visual.review(source['cameraId'],
                    'report-'+str(report['endAt'])+'-'+report['slot'],
                    [(source['imageUrl'].rsplit('/',1)[1],source['observedAt'])])
        except asyncio.CancelledError: raise
        except Exception: source['visualReview'] = dict(status='unavailable')
    return values


def visible_text(source):
    review = source.get('visualReview') or {}
    if review.get('status') != 'completed': return ''
    text = str((review.get('review') or {}).get('visible') or '').strip()
    # Only visual findings belong in the report. Never expose structured output
    # or upgrade a snapshot into an assurance about the whole home/time period.
    if not text or any(t in text for t in ('```','{"','http','绝对安全','很安全','一切正常','全程安全','没有发生任何','保证安全')): return ''
    clauses = [s.strip() for s in re.split(r'[；;。]', text) if s.strip()]
    clauses = [s for s in clauses if not any(k in s for k in ('SECURITY','时间戳','标识','显示白色文字','角显示'))]
    if not clauses: return ''
    focus = ('人','宠物','狗','猫','包裹','纸箱','遮挡','看不清')
    relevant = [s for s in clauses if any(k in s for k in focus)]
    concise = []
    for clause in (relevant or clauses)[:2]:
        if relevant:
            clause = '，'.join(part for part in clause.split('，') if any(k in part for k in focus))
        if len(clause)>65: clause = clause.split('，')[0]
        concise.append(clause)
    return '。'.join(concise)[:100].rstrip('。')+'。'


def present(message):
    """Rephrase old reports from their original evidence without rewriting history."""
    if not message.get('report') or not any(s.get('type')=='report_scope' for s in message.get('sources',[])): return message
    return message | render(message['report'],message['sources'])


def render(report, sources, selected=()):
    """Model output is used only for ranking known IDs, never factual prose."""
    scope = sources[0]
    zone = ZoneInfo(report['timezone'])
    stamp = lambda at: datetime.fromtimestamp(at, zone).strftime('%m月%d日 %H:%M')
    period = stamp(report['startAt'])+'—'+stamp(report['endAt'])
    greeting = '早间报告' if report['slot']=='morning' else '晚间报告'
    devices = [s for s in sources if s['type']=='report_device']
    tasks = [s for s in sources if s['type']=='report_task']
    # Unknown/model-injected IDs cannot hide mandatory coverage and alert counts.
    order = {key: i for i, key in enumerate(selected)}
    tasks.sort(key=lambda s: (s.get('alert')!='open', order.get(s['id'], 999), s['id']))
    pictures = [s for s in sources if s['type']=='report_picture' and visible_text(s)]
    parts = [greeting+' · '+period]
    opened = sum(t.get('alert')=='open' for t in tasks)
    unknown = sum(t['status']=='active' and t['result']=='unknown' for t in tasks)
    if opened:
        parts.append('有一件守护事项需要你看一下。' if opened==1 else f'有 {opened} 件守护事项需要你看一下。')
        parts.append('先看看'+display_name(tasks[0]['name'],'待确认的事项')+'。')
    if not devices:
        parts.append('还没有接入摄像头，我暂时看不到家里的情况。')
    elif pictures:
        parts.append('这段时间，我在已保存的画面里看到了这些：')
        for source in sorted(pictures,key=lambda s:s['observedAt']):
            parts.append(datetime.fromtimestamp(source['observedAt'],zone).strftime('%H:%M')+'，'+visible_text(source))
        if not opened and not unknown: parts.append('目前没有需要你处理的守护提醒。')
        parts.append('这些是已查看画面的情况，其他时段还不能确认。')
    elif scope.get('eventCount',0):
        kinds=scope.get('eventTypes',{})
        if kinds.get('门铃响起'): parts.append('这段时间收到了门铃响起的记录。')
        elif kinds.get('有人'): parts.append('摄像头记录到有人活动的信号。')
        elif kinds.get('包裹放下') or kinds.get('包裹取走'): parts.append('摄像头记录到包裹相关的活动。')
        else: parts.append('摄像头记录到了活动。')
        parts.append('但还没看清具体发生了什么，暂时不能确认是否有异常。')
    elif scope.get('sampleCount',0) or any(s['type']=='report_picture' for s in sources):
        parts.append('已经保存了这段时间的画面，但还没看清具体发生了什么。')
    else:
        parts.append('还没收到这段时间的画面，暂时不能确认家里的情况。')
    if unknown: parts.append('有交代给我的事情暂时没看清，等取得有效画面后再确认。')
    if any(d.get('failedSampling') for d in devices):
        parts.append('摄像头连接需要检查一下，打开 App 后我会尝试恢复。')
    return dict(title=LABELS[report['slot']], body='\n'.join(parts),
                why=period+' · '+report['timezone']+'；依据已保存记录整理。', sources=sources)
