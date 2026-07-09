from datetime import datetime, time

import pytest

from app import _lane_class, _prepare_slots


class TestLaneClass:
    def test_zero_free_is_level_0(self):
        assert _lane_class(0, 6) == "level-0"

    def test_full_free_is_level_6(self):
        assert _lane_class(6, 6) == "level-6"

    @pytest.mark.parametrize("free,total,expected", [
        (1, 6, "level-1"),   # 1/6 = 0.167 → exactly at boundary → level-1
        (2, 6, "level-2"),
        (3, 6, "level-3"),   # 3/6 = 0.5 ≤ 4/6 but > 3/6 → level-4... wait let me recalc
        (4, 6, "level-4"),
        (5, 6, "level-5"),
    ])
    def test_parametrized_levels(self, free, total, expected):
        assert _lane_class(free, total) == expected

    def test_8_lane_pool_full(self):
        assert _lane_class(8, 8) == "level-6"

    def test_8_lane_pool_zero(self):
        assert _lane_class(0, 8) == "level-0"

    def test_10_lane_pool_half(self):
        # 5/10 = 0.5, and 0.5 ≤ 3/6 = 0.5 → level-3
        assert _lane_class(5, 10) == "level-3"


class TestPrepareSlots:
    RAW = [
        {"weekday": "monday", "slot_start": "08:00", "slot_end": "08:30", "free_lanes": 3, "total_lanes": 6},
        {"weekday": "monday", "slot_start": "08:30", "slot_end": "09:00", "free_lanes": 0, "total_lanes": 6},
        {"weekday": "monday", "slot_start": "09:00", "slot_end": "09:30", "free_lanes": 6, "total_lanes": 6},
        {"weekday": "tuesday", "slot_start": "08:00", "slot_end": "08:30", "free_lanes": 2, "total_lanes": 6},
    ]

    def test_filters_to_selected_day(self):
        now = datetime(2024, 1, 15, 10, 0)
        result = _prepare_slots(self.RAW, "monday", now, False)
        assert all(s["weekday"] == "monday" for s in result)
        assert len(result) == 3

    def test_sorted_by_start(self):
        now = datetime(2024, 1, 15, 10, 0)
        result = _prepare_slots(self.RAW, "monday", now, False)
        starts = [s["slot_start"] for s in result]
        assert starts == sorted(starts)

    def test_css_class_added(self):
        now = datetime(2024, 1, 15, 10, 0)
        result = _prepare_slots(self.RAW, "monday", now, False)
        assert all("css_class" in s for s in result)

    def test_is_current_false_when_not_today(self):
        now = datetime(2024, 1, 15, 8, 15)
        result = _prepare_slots(self.RAW, "monday", now, is_today=False)
        assert all(not s["is_current"] for s in result)

    def test_is_current_true_for_active_slot(self):
        now = datetime(2024, 1, 15, 8, 15)  # 08:15 is within 08:00–08:30
        result = _prepare_slots(self.RAW, "monday", now, is_today=True)
        current = [s for s in result if s["is_current"]]
        assert len(current) == 1
        assert current[0]["slot_start"] == "08:00"

    def test_is_past_true_for_elapsed_slot(self):
        now = datetime(2024, 1, 15, 9, 0)  # 09:00 means 08:00–08:30 and 08:30–09:00 are past
        result = _prepare_slots(self.RAW, "monday", now, is_today=True)
        past = [s for s in result if s["is_past"]]
        assert len(past) == 2

    def test_slot_at_exact_end_is_past(self):
        now = datetime(2024, 1, 15, 8, 30)  # exactly at end of 08:00–08:30
        result = _prepare_slots(self.RAW, "monday", now, is_today=True)
        first = next(s for s in result if s["slot_start"] == "08:00")
        assert first["is_past"]
        assert not first["is_current"]

    def test_empty_for_unknown_day(self):
        now = datetime(2024, 1, 15, 10, 0)
        result = _prepare_slots(self.RAW, "wednesday", now, False)
        assert result == []
