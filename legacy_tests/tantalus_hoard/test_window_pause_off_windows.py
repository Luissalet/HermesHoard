"""Off Windows (Hermes moved to a Spark so the PC can be switched off) the open-window targets wait quietly: no fetch, no
failure, no "needs your help" mail; they keep their state and are looked at again later."""

import pytest

from tantalus_hoard import engine as eng


class FakeStore:
    def __init__(self):
        self.updates = []

    def update_target(self, target_id, **fields):
        self.updates.append((target_id, fields))


class FakeEngine:
    def __init__(self):
        self.store = FakeStore()
        self.clock = lambda: 1000.0

    def fetch_target(self, target, watcher):
        raise AssertionError("fetched")


def test_open_window_targets_pause_off_windows(monkeypatch):
    monkeypatch.setattr(eng, "WINDOWS_HOST", False)
    fake = FakeEngine()
    target = {"id": "t1", "fetch_tier": "open_window", "status": "active", "fail_count": 0}
    res = eng.Engine._check(fake, target, {"id": "w1", "config": {}}, revalidation=False)
    assert res["paused"] is True and res["events"] == []
    (tid, fields), = fake.store.updates
    assert tid == "t1" and fields["next_check_ts"] == 1000.0 + eng.PAUSED_RECHECK_S
    assert "Spark" in fields["last_error"] and "status" not in fields and "fail_count" not in fields


def test_other_targets_and_windows_hosts_still_fetch(monkeypatch):
    fake = FakeEngine()
    monkeypatch.setattr(eng, "WINDOWS_HOST", False)
    with pytest.raises(AssertionError, match="fetched"):
        eng.Engine._check(fake, {"id": "t2", "fetch_tier": "http"}, {"id": "w1", "config": {}}, revalidation=False)
    monkeypatch.setattr(eng, "WINDOWS_HOST", True)
    with pytest.raises(AssertionError, match="fetched"):
        eng.Engine._check(fake, {"id": "t3", "fetch_tier": "open_window"}, {"id": "w1", "config": {}}, revalidation=False)
