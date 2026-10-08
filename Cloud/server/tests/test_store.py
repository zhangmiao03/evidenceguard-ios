from pathlib import Path

import pytest

from evidenceguard.store import Store


@pytest.fixture
def store(tmp_path: Path):
    value = Store(tmp_path / "test.sqlite3")
    yield value
    value.close()


def test_skill_requires_explicit_confirmation_and_revision(store: Store):
    draft = store.create_draft("看住这个箱子", ["cam-a", "cam-b"])
    assert draft["status"] == "draft"
    revised = store.update_draft(draft["id"], draft["target"], draft["regions"])
    assert revised["revision"] == 2
    with pytest.raises(ValueError):
        store.confirm(draft["id"], 1)
    active = store.confirm(draft["id"], 2)
    assert active["status"] == "active"
    assert active["result"] == "initializing"


def test_target_and_regions_are_separate(store: Store):
    draft = store.create_draft("看住这个箱子", ["cam-a"])
    assert draft["target"]["box"] != draft["regions"]["cam-a"]


def test_events_are_strictly_sequenced(store: Store):
    store.event("run-1", "one", {})
    store.event("run-1", "two", {})
    assert [item["sequence"] for item in store.events("run-1")] == [1, 2]


def test_alert_does_not_complete_continuous_skill(store: Store):
    skill = store.create_draft("看住这个箱子", ["cam-a"])
    skill = store.confirm(skill["id"], skill["revision"])
    lab = {"task": {"result": "needs_attention", "reason": "目标已移出守护区域", "alert": "open", "evidence": []}}
    updated = store.sync_observation(skill["id"], lab)
    assert updated["status"] == "active"
    assert updated["alert"] == "open"


def test_stable_state_does_not_flood_evidence(store: Store):
    skill = store.create_draft("看住这个箱子", ["cam-a"])
    skill = store.confirm(skill["id"], skill["revision"])
    observation = {"frame_id": "cam-a-1-1", "device_id": "cam-a", "captured_at": 1.0, "relation": "inside", "reason": "区内", "source_type": "fixture"}
    lab = {"task": {"result": "confirmed", "reason": "目标位于守护区域内", "alert": "none", "evidence": [observation]}}
    store.sync_observation(skill["id"], lab)
    observation["frame_id"], observation["captured_at"] = "cam-a-1-2", 2.0
    store.sync_observation(skill["id"], lab)
    assert len(store.evidence()) == 1
