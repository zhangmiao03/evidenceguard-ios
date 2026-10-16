"""Acceptance must not confuse Codex receipts with direct model HTTP metrics."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('demo_smoke', Path(__file__).with_name('smoke.py'))
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def evidence(executor):
    names = ['list_camera_capabilities', 'list_tasks']
    run = dict(status='completed', executionContract=dict(executor=executor),
               toolReceipts=[dict(tool=n, status='completed') for n in names])
    events = [dict(type=k, payload=dict(executor=executor)) for k in
              ('executor_started', 'executor_completed', 'response_completed')]
    rows = [dict(name='tool.finished', kind='tool', data=dict(tool=n)) for n in names]
    return run, events, rows


def test_codex_requires_lifecycle_and_tools_without_inventing_http_metrics():
    result = smoke.verify_receipts(*evidence('codex-app-server-v1'))
    assert result['codexLifecycleVerified'] is True
    assert result['realModelCalls'] is None and 'models' not in result


@pytest.mark.parametrize('missing', ['executor_started', 'executor_completed', 'response_completed'])
def test_codex_does_not_pass_with_incomplete_execution(missing):
    run, events, rows = evidence('codex-app-server-v1')
    with pytest.raises(AssertionError):
        smoke.verify_receipts(run, [e for e in events if e['type'] != missing], rows)


def test_legacy_executor_still_requires_real_http_receipts():
    run, events, rows = evidence('bounded-chat-v1')
    with pytest.raises(AssertionError):
        smoke.verify_receipts(run, events, rows)
    rows += [dict(name='model.completed', kind='model', data=dict(model='test-model', httpStatus=200)) for _ in range(2)]
    assert smoke.verify_receipts(run, events, rows)['realModelCalls'] == 2
    rows[-1]['data']['httpStatus'] = 500
    with pytest.raises(AssertionError):
        smoke.verify_receipts(run, events, rows)


@pytest.mark.parametrize('unexpected', ['hardware', 'capture', 'extra-tool', 'failed-tool', 'unknown-executor', 'observer-missing'])
def test_mutation_and_unverified_receipts_do_not_pass(unexpected):
    run, events, rows = evidence('codex-app-server-v1')
    if unexpected == 'hardware': run['hardwareOperations'] = [dict(id='unexpected')]
    if unexpected == 'capture': run['captures'] = [dict(id='unexpected')]
    if unexpected == 'extra-tool': run['toolReceipts'].append(dict(tool='enable_task', status='completed'))
    if unexpected == 'failed-tool': run['toolReceipts'][0]['status'] = 'failed'
    if unexpected == 'unknown-executor': run['executionContract']['executor'] = 'unverified'
    if unexpected == 'observer-missing': rows.clear()
    with pytest.raises(AssertionError):
        smoke.verify_receipts(run, events, rows)
