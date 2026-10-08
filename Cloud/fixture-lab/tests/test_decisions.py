import copy
from dataclasses import asdict
import pytest
from backend.domain import Observation, evaluate, new_task, reset_pending


def obs(t, relation='inside', camera='cam-a', revision=1, frame_id=None):
    return Observation(frame_id or f'{camera}-{t}', camera, t, t+.1, revision, relation, 'test')


def confirm(task, relation='inside', start=101, camera='cam-a'):
    events = []
    for t in (start, start+1):
        events += evaluate(task, {camera:obs(t,relation,camera)}, t+.2)
    return events


def test_new_task_is_not_initially_confirmed():
    task = new_task(100)
    assert task['result'] == 'initializing'
    evaluate(task, {}, 101)
    assert task['result'] == 'unknown'


def test_fresh_observations_required_for_normal_and_alert():
    for relation, result in [('inside','confirmed'),('outside','needs_attention')]:
        task = new_task(100)
        evaluate(task, {'cam-a':obs(101,relation)}, 101.2)
        assert task['result'] == 'unknown'
        evaluate(task, {'cam-a':obs(102,relation)}, 102.2)
        assert task['result'] == result


def test_duplicate_frame_does_not_confirm():
    task = new_task(100)
    for t in (101.1, 102, 103):
        evaluate(task, {'cam-a':obs(101)}, t)
    assert task['result'] == 'unknown'
    assert task['candidate_count'] == 1


def test_disappearance_is_unknown_not_outside():
    task = new_task(100)
    confirm(task)
    evaluate(task, {'cam-a':obs(103,'unknown')}, 103)
    assert task['result'] == 'unknown'
    assert task['alert'] == 'none'


def test_outside_boundary_outside_is_not_consecutive():
    task = new_task(100)
    for t, relation in [(101,'outside'),(102,'unknown'),(103,'outside')]:
        evaluate(task, {'cam-a':obs(t,relation)}, t)
    assert task['alert'] == 'none'


def test_alert_dedup_unknown_preserves_unresolved_then_recovery():
    task = new_task(100)
    events = []
    for t in range(101,108):
        events += evaluate(task, {'cam-a':obs(t,'outside')}, t)
    assert sum(e['type']=='alert_opened' for e in events) == 1
    evaluate(task, {}, 120)
    assert task['result']=='unknown' and task['alert']=='open'
    events = confirm(task, start=121)
    assert task['alert']=='resolved'
    assert sum(e['type']=='alert_resolved' for e in events) == 1
    assert task['episode']==1


def test_recheck_requires_new_capture_and_keeps_acknowledgement():
    task = new_task(100)
    confirm(task, 'outside')
    task['alert']='acknowledged'
    reset_pending(task, 105, 'recheck')
    evaluate(task, {'cam-a':obs(104)}, 105)
    assert task['result']=='unknown' and task['alert']=='acknowledged'
    confirm(task, start=106)
    assert task['alert']=='resolved'


def test_no_frames_timer_expires_evidence():
    task = new_task(100)
    confirm(task)
    evaluate(task, {'cam-a':obs(102)}, 110)
    assert task['result']=='unknown'
    assert task['last_confirmed_at']==102


def test_second_camera_can_confirm_when_primary_occluded():
    task = new_task(100)
    for t in (101,102):
        evaluate(task, {'cam-a':obs(t,'unknown'),'cam-b':obs(t,'inside','cam-b')}, t)
    assert task['result']=='confirmed'
    assert task['evidence'][0]['device_id']=='cam-b'


def test_stale_secondary_cannot_confirm_new_primary_observation():
    task = new_task(100)
    confirm(task,start=101,camera='cam-b')
    evaluate(task, {'cam-a':obs(105,'unknown'),'cam-b':obs(102,'inside','cam-b')},105)
    assert task['result']=='unknown'


def test_conflict_is_unknown():
    task = new_task(100)
    for t in (101,102):
        evaluate(task, {'cam-a':obs(t,'outside'),'cam-b':obs(t,'inside','cam-b')},t)
    assert task['result']=='unknown'
    assert '冲突' in task['reason']
    assert {o['device_id'] for o in task['evidence']} == {'cam-a', 'cam-b'}


def test_old_revision_and_future_timestamps_rejected():
    task = new_task(100)
    task['revision']=2
    evaluate(task, {'cam-a':obs(101,revision=1)},101)
    assert task['result']=='unknown'
    evaluate(task, {'cam-a':obs(120,revision=2)},101)
    assert task['result']=='unknown'


def test_pause_preserves_task_and_alert():
    task = new_task(100)
    confirm(task,'outside')
    task['lifecycle']='paused'
    previous=copy.deepcopy(task)
    assert evaluate(task,{},200)==[]
    assert task==previous


def test_large_time_gap_restarts_confirmation():
    task=new_task(100)
    evaluate(task,{'cam-a':obs(101)},101)
    evaluate(task,{'cam-a':obs(106)},106)
    assert task['result']=='unknown'
