"""Subscribed home reports: wall-clock scheduling and evidence-owned wording.

The model may rank existing facts, but cannot turn missing telemetry into safety,
invent identity, or decide whether a subscribed report is worth delivering.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, time as clock_time, timedelta
import json
import re
from zoneinfo import ZoneInfo

from .camera.sources import REAL_SOURCES

SLOTS = ('morning', 'evening')
LABELS = {'morning': '早安报告', 'evening': '晚间报告'}
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
    """Only the latest due slot is caught up. DST folds deliver once per local day.

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
    return dict(slot=slot, localDate=date, timezone=p['timezone'], startAt=past[-2][0],
                endAt=end, expiresAt=future[0][0], schedule=schedule_signature(p))


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
    return sources


def render(report, sources, selected=()):
    """Model output is used only for ranking known IDs, never factual prose."""
    scope = sources[0]
    zone = ZoneInfo(report['timezone'])
    stamp = lambda at: datetime.fromtimestamp(at, zone).strftime('%m月%d日 %H:%M')
    period = stamp(report['startAt'])+'—'+stamp(report['endAt'])
    greeting = '早上好' if report['slot']=='morning' else '晚上好'
    devices = [s for s in sources if s['type']=='report_device']
    tasks = [s for s in sources if s['type']=='report_task']
    # Unknown/model-injected IDs cannot hide mandatory coverage and alert counts.
    order = {key: i for i, key in enumerate(selected)}
    tasks.sort(key=lambda s: (s.get('alert')!='open', order.get(s['id'], 999), s['id']))
    parts = [f'{greeting}，{period}的家里记录整理好了。']
    if not devices:
        parts.append('还没有接入摄像头，目前无法判断家里的情况。')
    else:
        if scope['eventCount'] or scope['sampleCount']:
            parts.append(f"这段时间保存了 {scope['eventCount']} 条设备事件、{scope['sampleCount']} 次画面取样。")
            if scope['eventTypes']:
                parts.append('设备标记：'+'、'.join(f'{k} {v} 次' for k, v in sorted(scope['eventTypes'].items()))+'；标签还需要结合画面确认。')
        else:
            parts.append('这段时间没有收到新的事件或画面，不能据此判断一切正常。')
        missing = [d for d in devices if not d['hasPeriodData']]
        if missing:
            detail = []
            for index, d in enumerate(missing[:2], 1):
                detail.append(display_name(d['name'],f'摄像头 {index}')+('最近记录在 '+stamp(d['lastRecordAt']) if d['lastRecordAt'] else '尚无记录'))
            parts.append(f'{len(missing)} 台摄像头缺少本时段记录：'+'；'.join(detail)+'。')
        if any(d['failedSampling'] for d in devices):
            parts.append('有定时取样未完成，可以检查摄像头和采集端的连接。')
        opened = sum(t.get('alert')=='open' for t in tasks)
        unknown = sum(t['status']=='active' and t['result']=='unknown' for t in tasks)
        parts.append(f'当前有 {opened} 项任务提醒待确认。' if opened else '当前没有未处理的任务提醒。')
        if unknown:
            parts.append(f'另有 {unknown} 项运行中任务的观察结果无法确认。')
        if tasks:
            parts.append('可以先看看'+display_name(tasks[0]['name'],'待确认任务')+'。')
        parts.append('这些是离散记录，尚不能确认整段时间的情况。')
    return dict(title=LABELS[report['slot']], body='\n'.join(parts),
                why=period+' · '+report['timezone']+'；仅依据已保存记录，未启用或操作设备。', sources=sources)
