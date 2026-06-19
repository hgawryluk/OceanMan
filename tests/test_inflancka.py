import re

import pytest

from models import PoolSchedule, SlotReading
from pools import inflancka

TIME_RE = re.compile(r"^\d{2}:\d{2}$")
ALL_WEEKDAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}


@pytest.fixture(scope="module")
def schedule(inflancka_fixture):
    data, url, md5 = inflancka_fixture
    return inflancka.parse(data, url, md5)


class TestParserSuccess:
    def test_returns_pool_schedule(self, schedule):
        assert isinstance(schedule, PoolSchedule)

    def test_pool_name(self, schedule):
        assert schedule.pool == "inflancka"

    def test_source_url_set(self, schedule):
        assert schedule.source_url

    def test_source_hash_set(self, schedule):
        assert schedule.source_hash

    def test_slots_not_empty(self, schedule):
        assert len(schedule.slots) > 0

    def test_all_slots_are_slot_readings(self, schedule):
        assert all(isinstance(s, SlotReading) for s in schedule.slots)


class TestSlotCount:
    def test_total_slot_count(self, schedule):
        # 10-lane pool, 15-min slots across 7 days — fixture: week 15–21 Jun 2026
        assert len(schedule.slots) == 425

    def test_all_weekdays_present(self, schedule):
        found = {s.weekday for s in schedule.slots}
        assert found == ALL_WEEKDAYS

    def test_monday_slot_count(self, schedule):
        monday = [s for s in schedule.slots if s.weekday == "monday"]
        assert len(monday) == 61

    def test_friday_slot_count(self, schedule):
        friday = [s for s in schedule.slots if s.weekday == "friday"]
        assert len(friday) == 61

    def test_saturday_slot_count(self, schedule):
        saturday = [s for s in schedule.slots if s.weekday == "saturday"]
        assert len(saturday) == 60


class TestSlotIntegrity:
    def test_total_lanes_always_10(self, schedule):
        assert all(s.total_lanes == 10 for s in schedule.slots)

    def test_free_lanes_within_bounds(self, schedule):
        assert all(0 <= s.free_lanes <= s.total_lanes for s in schedule.slots)

    def test_pool_field_on_all_slots(self, schedule):
        assert all(s.pool == "inflancka" for s in schedule.slots)

    def test_slot_start_format(self, schedule):
        assert all(TIME_RE.match(s.slot_start) for s in schedule.slots)

    def test_slot_end_format(self, schedule):
        assert all(TIME_RE.match(s.slot_end) for s in schedule.slots)

    def test_slot_start_before_end(self, schedule):
        assert all(s.slot_start < s.slot_end for s in schedule.slots)

    def test_weekday_values_valid(self, schedule):
        assert all(s.weekday in ALL_WEEKDAYS for s in schedule.slots)


class TestKnownSlotValues:
    """Anchor tests against specific slots from the fixture PDF (week 15–21 Jun 2026)."""

    def _get(self, schedule, weekday, slot_start):
        hits = [s for s in schedule.slots if s.weekday == weekday and s.slot_start == slot_start]
        assert hits, f"No slot found for {weekday} {slot_start}"
        return hits[0]

    def test_monday_first_slot(self, schedule):
        s = self._get(schedule, "monday", "06:15")
        assert s.slot_end == "06:30"
        assert s.free_lanes == 1
        assert s.total_lanes == 10

    def test_monday_last_slot(self, schedule):
        monday = [s for s in schedule.slots if s.weekday == "monday"]
        last = max(monday, key=lambda s: s.slot_start)
        assert last.slot_start == "21:15"
        assert last.slot_end == "21:30"
        assert last.free_lanes == 8

    def test_friday_first_slot(self, schedule):
        s = self._get(schedule, "friday", "06:15")
        assert s.slot_end == "06:30"
        assert s.free_lanes == 1

    def test_friday_last_slot(self, schedule):
        friday = [s for s in schedule.slots if s.weekday == "friday"]
        last = max(friday, key=lambda s: s.slot_start)
        assert last.slot_start == "21:15"
        assert last.free_lanes == 8

    def test_saturday_first_slot(self, schedule):
        saturday = [s for s in schedule.slots if s.weekday == "saturday"]
        first = min(saturday, key=lambda s: s.slot_start)
        assert first.slot_start == "06:30"
        assert first.free_lanes == 9
