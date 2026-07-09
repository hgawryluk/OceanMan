from datetime import datetime

import pytest

import store
from models import PoolSchedule, SlotReading


def _make_schedule(pool="testpool", source_hash="abc123", free=3, slots=1):
    slot_list = [
        SlotReading(pool=pool, weekday="monday", slot_start="08:00", slot_end="08:30",
                    free_lanes=free, total_lanes=6)
        for _ in range(slots)
    ]
    return PoolSchedule(
        pool=pool,
        valid_from=None,
        fetched_at=datetime(2024, 6, 15, 10, 0),
        source_url=f"https://example.com/{pool}.pdf",
        source_hash=source_hash,
        slots=slot_list,
    )


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "test.db")
    store.init_db()


class TestUpsertAndGet:
    def test_get_returns_none_when_empty(self):
        assert store.get_schedule("testpool") is None

    def test_upsert_then_get(self):
        store.upsert_schedule(_make_schedule())
        result = store.get_schedule("testpool")
        assert result is not None
        assert result["schedule"]["pool"] == "testpool"

    def test_slots_stored_correctly(self):
        store.upsert_schedule(_make_schedule(free=5, slots=2))
        result = store.get_schedule("testpool")
        assert len(result["slots"]) == 2
        assert result["slots"][0]["free_lanes"] == 5

    def test_duplicate_hash_is_no_op(self):
        store.upsert_schedule(_make_schedule(source_hash="dup"))
        store.upsert_schedule(_make_schedule(source_hash="dup", free=99))
        result = store.get_schedule("testpool")
        assert result["slots"][0]["free_lanes"] == 3  # first insert wins

    def test_new_hash_replaces_old_schedule(self):
        store.upsert_schedule(_make_schedule(source_hash="v1", free=1))
        store.upsert_schedule(_make_schedule(source_hash="v2", free=6))
        result = store.get_schedule("testpool")
        assert result["slots"][0]["free_lanes"] == 6

    def test_old_slots_removed_on_replace(self):
        store.upsert_schedule(_make_schedule(source_hash="v1", slots=5))
        store.upsert_schedule(_make_schedule(source_hash="v2", slots=2))
        result = store.get_schedule("testpool")
        assert len(result["slots"]) == 2

    def test_different_pools_are_independent(self):
        store.upsert_schedule(_make_schedule(pool="alpha", source_hash="a1"))
        store.upsert_schedule(_make_schedule(pool="beta", source_hash="b1"))
        assert store.get_schedule("alpha") is not None
        assert store.get_schedule("beta") is not None
        assert store.get_schedule("gamma") is None


class TestGetLastHash:
    def test_returns_none_when_no_schedule(self):
        assert store.get_last_hash("testpool") is None

    def test_returns_hash_after_upsert(self):
        store.upsert_schedule(_make_schedule(source_hash="myhash"))
        assert store.get_last_hash("testpool") == "myhash"

    def test_returns_latest_hash_after_replace(self):
        store.upsert_schedule(_make_schedule(source_hash="old"))
        store.upsert_schedule(_make_schedule(source_hash="new"))
        assert store.get_last_hash("testpool") == "new"


class TestFetchLog:
    def test_get_last_fetch_entry_none_when_empty(self):
        assert store.get_last_fetch_entry("testpool") is None

    def test_log_fetch_changed(self):
        store.log_fetch("testpool", True, "42 slots")
        entry = store.get_last_fetch_entry("testpool")
        assert entry["changed"] == 1
        assert entry["note"] == "42 slots"

    def test_log_fetch_no_change(self):
        store.log_fetch("testpool", False, "no change")
        entry = store.get_last_fetch_entry("testpool")
        assert entry["changed"] == 0
        assert entry["note"] == "no change"

    def test_get_last_fetch_entry_returns_most_recent(self):
        store.log_fetch("testpool", False, "first")
        store.log_fetch("testpool", True, "second")
        entry = store.get_last_fetch_entry("testpool")
        assert entry["note"] == "second"

    def test_log_fetch_default_note(self):
        store.log_fetch("testpool", False)
        entry = store.get_last_fetch_entry("testpool")
        assert entry["note"] == ""
