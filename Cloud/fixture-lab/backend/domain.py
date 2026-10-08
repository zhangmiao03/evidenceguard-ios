"""Evidence-based decisions, independent of transport, simulator and UI."""
from dataclasses import dataclass, field, asdict
from typing import Literal


@dataclass
class Observation:
    frame_id: str
    device_id: str
    captured_at: float
    received_at: float
    revision: int
    relation: Literal['inside', 'outside', 'unknown']
    reason: str
    bbox: list[float] | None = None
    marker_ids: list[int] = field(default_factory=list)
    source_type: str = 'fixture'
    channel_id: str = 'main'


def new_task(now: float) -> dict:
    return dict(id='watch-box', title='看住门口的箱子', revision=1,
                lifecycle='active', result='initializing', reason='等待首次有效观察',
                alert='none', episode=0, last_confirmed_at=None, evidence=[],
                roi={'cam-a': [.17, .27, .65, .81], 'cam-b': [.25, .24, .76, .81]},
                target_marker=17, freshness_seconds=6, max_skew_seconds=2,
                confirmations=2, not_before=now, candidate=None, candidate_count=0,
                candidate_time=0, candidate_proof=None, last_evaluated={},
                last_result_at=now)


def reset_pending(task: dict, now: float, reason: str):
    task.update(result='unknown', reason=reason, not_before=now, candidate=None,
                candidate_count=0, candidate_proof=None, last_evaluated={}, evidence=[])


def evaluate(task: dict, latest: dict[str, Observation], now: float) -> list[dict]:
    """A timer invokes this even without frames. Return durable business events."""
    if task['lifecycle'] != 'active':
        return []
    previous = task['result']
    valid = []
    for obs in latest.values():
        if (obs.revision == task['revision'] and obs.captured_at >= task['not_before']
                and -.5 <= now - obs.captured_at <= task['freshness_seconds']
                and obs.relation in ('inside', 'outside')):
            valid.append(obs)
    reason = '没有新鲜且能确认目标位置的画面'
    chosen = None
    if valid:
        valid.sort(key=lambda o: (o.device_id != 'cam-a', -o.captured_at))
        if len(valid) > 1 and len({o.relation for o in valid}) > 1:
            reason = '两个视角的有效证据冲突，需要重新观察'
        else:
            # Reject an old secondary frame when the primary has a newer ambiguous observation.
            chosen = valid[0]
            primary = latest.get('cam-a')
            if chosen.device_id != 'cam-a' and primary and primary.revision == task['revision']:
                if primary.captured_at - chosen.captured_at > task['max_skew_seconds']:
                    chosen = None
                    reason = '第二视角落后于当前观察，不能用于补证'
    events = []
    if chosen is None:
        context = [asdict(o) for o in latest.values() if o.revision == task['revision']]
        task.update(result='unknown', reason=reason, candidate=None, candidate_count=0,
                    candidate_proof=None, evidence=context)
    else:
        target = 'confirmed' if chosen.relation == 'inside' else 'needs_attention'
        proof = chosen.frame_id
        task['evidence'] = [asdict(chosen)]
        if task['last_evaluated'].get(chosen.device_id) != proof:
            task['last_evaluated'][chosen.device_id] = proof
            key = f'{target}:{chosen.device_id}'
            if task['candidate'] == key and 0 < chosen.captured_at-task['candidate_time'] <= 3:
                task['candidate_count'] += 1
            else:
                task['candidate'], task['candidate_count'] = key, 1
            task['candidate_time'], task['candidate_proof'] = chosen.captured_at, proof
        if task['candidate_count'] >= task['confirmations']:
            task.update(result=target, last_confirmed_at=chosen.captured_at,
                        reason=('目标位于守护区域内' if target == 'confirmed' else '目标已移出守护区域')
                        + (' · 第二视角补证' if chosen.device_id == 'cam-b' else ''))
            if target == 'needs_attention' and task['alert'] not in ('open', 'acknowledged'):
                task['episode'] += 1
                task['alert'] = 'open'
                events.append(dict(type='alert_opened', text='箱子移出守护区域', episode=task['episode']))
            elif target == 'confirmed' and task['alert'] in ('open', 'acknowledged'):
                task['alert'] = 'resolved'
                events.append(dict(type='alert_resolved', text='新证据确认箱子已回到区域内', episode=task['episode']))
        else:
            task.update(result='unknown', reason='正在等待第二次独立观察', evidence=[asdict(chosen)])
    if task['result'] != previous:
        task['last_result_at'] = now
        events.append(dict(type='state_changed', text=task['reason'], previous=previous, result=task['result']))
    for e in events:
        e.update(at=now, revision=task['revision'], evidence=list(task['evidence']))
    return events
