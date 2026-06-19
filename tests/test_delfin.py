import re

import pytest

from models import PoolSchedule, SlotReading
from pools import delfin

TIME_RE = re.compile(r"^\d{2}:\d{2}$")
ALL_WEEKDAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}


@pytest.fixture(scope="module")
def schedule(delfin_fixture):
    data, url, md5 = delfin_fixture
    # Fixture is an XLSX — pass a URL that contains .xlsx so the parser dispatches correctly
    xlsx_url = "https://example.com/fixture/delfin.xlsx"
    return delfin.parse(data, xlsx_url, md5)


class TestParserSuccess:
    def test_returns_pool_schedule(self, schedule):
        assert isinstance(schedule, PoolSchedule)

    def test_pool_name(self, schedule):
        assert schedule.pool == "delfin"

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
        # 6-lane pool, 30-min slots, 7 days — fixture: week 15–21 Jun 2026
        assert len(schedule.slots) == 210

    def test_all_weekdays_present(self, schedule):
        found = {s.weekday for s in schedule.slots}
        assert found == ALL_WEEKDAYS

    def test_monday_slot_count(self, schedule):
        monday = [s for s in schedule.slots if s.weekday == "monday"]
        assert len(monday) == 30

    def test_saturday_slot_count(self, schedule):
        saturday = [s for s in schedule.slots if s.weekday == "saturday"]
        assert len(saturday) == 30


class TestSlotIntegrity:
    def test_total_lanes_always_6(self, schedule):
        assert all(s.total_lanes == 6 for s in schedule.slots)

    def test_free_lanes_within_bounds(self, schedule):
        assert all(0 <= s.free_lanes <= s.total_lanes for s in schedule.slots)

    def test_pool_field_on_all_slots(self, schedule):
        assert all(s.pool == "delfin" for s in schedule.slots)

    def test_slot_start_format(self, schedule):
        assert all(TIME_RE.match(s.slot_start) for s in schedule.slots)

    def test_slot_end_format(self, schedule):
        assert all(TIME_RE.match(s.slot_end) for s in schedule.slots)

    def test_slot_start_before_end(self, schedule):
        assert all(s.slot_start < s.slot_end for s in schedule.slots)

    def test_weekday_values_valid(self, schedule):
        assert all(s.weekday in ALL_WEEKDAYS for s in schedule.slots)

    def test_slots_are_30_minute_intervals(self, schedule):
        for s in schedule.slots:
            h0, m0 = map(int, s.slot_start.split(":"))
            h1, m1 = map(int, s.slot_end.split(":"))
            duration = (h1 * 60 + m1) - (h0 * 60 + m0)
            assert duration == 30, f"Unexpected duration {duration} for {s}"


class TestKnownSlotValues:
    """Anchor tests against specific slots from the fixture XLSX (week 15–21 Jun 2026)."""

    def _get(self, schedule, weekday, slot_start):
        hits = [s for s in schedule.slots if s.weekday == weekday and s.slot_start == slot_start]
        assert hits, f"No slot found for {weekday} {slot_start}"
        return hits[0]

    def test_monday_first_slot(self, schedule):
        s = self._get(schedule, "monday", "07:00")
        assert s.slot_end == "07:30"
        assert s.free_lanes == 6
        assert s.total_lanes == 6

    def test_monday_last_slot(self, schedule):
        monday = [s for s in schedule.slots if s.weekday == "monday"]
        last = max(monday, key=lambda s: s.slot_start)
        assert last.slot_start == "21:30"
        assert last.slot_end == "22:00"
        assert last.free_lanes == 6

    def test_saturday_first_slot(self, schedule):
        s = self._get(schedule, "saturday", "07:00")
        assert s.slot_end == "07:30"
        assert s.free_lanes == 0

    def test_all_days_start_at_0700(self, schedule):
        for day in ALL_WEEKDAYS:
            slots = sorted(
                [s for s in schedule.slots if s.weekday == day],
                key=lambda s: s.slot_start,
            )
            assert slots[0].slot_start == "07:00", f"{day} doesn't start at 07:00"

    def test_all_days_end_at_2200(self, schedule):
        for day in ALL_WEEKDAYS:
            slots = sorted(
                [s for s in schedule.slots if s.weekday == day],
                key=lambda s: s.slot_start,
            )
            assert slots[-1].slot_end == "22:00", f"{day} doesn't end at 22:00"
