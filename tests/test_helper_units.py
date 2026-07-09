"""Unit tests for pure helper functions across pool parsers."""
import pytest

from pools.foka import _is_white as foka_is_white
from pools.potocka import _is_white as potocka_is_white, _parse_time
from pools.inflancka import _color_is_free, LANE_NUMS, FREE_COLOR


class TestIsWhite:
    """Same logic in foka and potocka — test both."""

    @pytest.mark.parametrize("fn", [foka_is_white, potocka_is_white])
    def test_none_is_white(self, fn):
        assert fn(None) is True

    @pytest.mark.parametrize("fn", [foka_is_white, potocka_is_white])
    def test_high_grayscale_is_white(self, fn):
        assert fn(0.9) is True

    @pytest.mark.parametrize("fn", [foka_is_white, potocka_is_white])
    def test_low_grayscale_is_not_white(self, fn):
        assert fn(0.5) is False

    @pytest.mark.parametrize("fn", [foka_is_white, potocka_is_white])
    def test_rgb_white(self, fn):
        assert fn([1.0, 1.0, 1.0]) is True

    @pytest.mark.parametrize("fn", [foka_is_white, potocka_is_white])
    def test_rgb_near_white(self, fn):
        assert fn([0.9, 0.9, 0.9]) is True

    @pytest.mark.parametrize("fn", [foka_is_white, potocka_is_white])
    def test_rgb_red_is_not_white(self, fn):
        assert fn([1.0, 0.0, 0.0]) is False

    @pytest.mark.parametrize("fn", [foka_is_white, potocka_is_white])
    def test_cmyk_all_zeros_is_white(self, fn):
        assert fn([0, 0, 0, 0]) is True

    @pytest.mark.parametrize("fn", [foka_is_white, potocka_is_white])
    def test_cmyk_with_ink_is_not_white(self, fn):
        assert fn([0.5, 0.0, 0.0, 0.0]) is False

    @pytest.mark.parametrize("fn", [foka_is_white, potocka_is_white])
    def test_threshold_boundary(self, fn):
        # Exactly at threshold (0.85) should be white
        assert fn(0.85) is True
        assert fn(0.849) is False


class TestColorIsFree:
    def test_exact_free_color_is_free(self):
        assert _color_is_free(FREE_COLOR) is True

    def test_within_tolerance_is_free(self):
        tweaked = tuple(c + 0.02 for c in FREE_COLOR)
        assert _color_is_free(tweaked) is True

    def test_outside_tolerance_is_not_free(self):
        wrong = (0.0, 0.0, 0.0)
        assert _color_is_free(wrong) is False

    def test_red_is_not_free(self):
        assert _color_is_free((1.0, 0.0, 0.0)) is False

    def test_none_is_not_free(self):
        assert _color_is_free(None) is False

    def test_too_short_is_not_free(self):
        assert _color_is_free((0.7,)) is False

    def test_empty_is_not_free(self):
        assert _color_is_free(()) is False


class TestLaneNums:
    def test_contains_lanes_0_to_9(self):
        # Inflancka labels its lanes 0–9 (10 lanes total)
        assert LANE_NUMS == {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9"}

    def test_does_not_contain_ten(self):
        assert "10" not in LANE_NUMS

    def test_size_is_10(self):
        assert len(LANE_NUMS) == 10


class TestParseTime:
    def test_valid_time(self):
        assert _parse_time("8.00-8.15") == ("08:00", "08:15")

    def test_two_digit_hours(self):
        assert _parse_time("10.00-10.15") == ("10:00", "10:15")

    def test_late_evening(self):
        assert _parse_time("22.45-23.00") == ("22:45", "23:00")

    def test_invalid_returns_none(self):
        assert _parse_time("not a time") is None

    def test_empty_returns_none(self):
        assert _parse_time("") is None

    def test_whitespace_stripped(self):
        assert _parse_time("  8.00-8.15  ") == ("08:00", "08:15")
