"""Tests for PredictionClock — verify Polymarket-aligned 12:00 UTC anchors."""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.prediction_clock import (
    DEFAULT_BLACKOUT_MINUTES,
    POLYMARKET_DAILY_RESOLVE_UTC_HOUR,
    PredictionClock,
    build_time_anchor,
)


@pytest.fixture
def clock() -> PredictionClock:
    return PredictionClock()


def _utc(year, month, day, hour=0, minute=0, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


class TestCurrentResolveAnchor:
    def test_before_noon_returns_today_noon(self, clock):
        now = _utc(2026, 5, 11, 8, 30)
        expected = _utc(2026, 5, 11, 12, 0)
        assert clock.current_resolve_anchor(now) == expected

    def test_at_noon_returns_today_noon(self, clock):
        now = _utc(2026, 5, 11, 12, 0)
        expected = _utc(2026, 5, 11, 12, 0)
        assert clock.current_resolve_anchor(now) == expected

    def test_one_second_after_noon_rolls_to_tomorrow(self, clock):
        now = _utc(2026, 5, 11, 12, 0, 1)
        expected = _utc(2026, 5, 12, 12, 0)
        assert clock.current_resolve_anchor(now) == expected

    def test_late_night_returns_next_day_noon(self, clock):
        now = _utc(2026, 5, 11, 23, 59)
        expected = _utc(2026, 5, 12, 12, 0)
        assert clock.current_resolve_anchor(now) == expected

    def test_naive_datetime_treated_as_utc(self, clock):
        now = datetime(2026, 5, 11, 8, 0)  # naive
        expected = _utc(2026, 5, 11, 12, 0)
        assert clock.current_resolve_anchor(now) == expected

    def test_non_utc_timezone_converted(self, clock):
        # 20:00 HK == 12:00 UTC
        hk = timezone(timedelta(hours=8))
        now = datetime(2026, 5, 11, 19, 30, tzinfo=hk)  # 11:30 UTC
        expected = _utc(2026, 5, 11, 12, 0)
        assert clock.current_resolve_anchor(now) == expected


class TestPreviousAndNextAnchor:
    def test_previous_is_24h_before_current(self, clock):
        now = _utc(2026, 5, 11, 8, 0)
        assert clock.previous_resolve_anchor(now) == _utc(2026, 5, 10, 12, 0)

    def test_next_is_24h_after_current(self, clock):
        now = _utc(2026, 5, 11, 8, 0)
        assert clock.next_resolve_anchor(now) == _utc(2026, 5, 12, 12, 0)


class TestTimeToResolve:
    def test_positive_before_resolve(self, clock):
        now = _utc(2026, 5, 11, 11, 0)
        ttr = clock.time_to_resolve(now)
        assert ttr == timedelta(hours=1)

    def test_zero_at_resolve(self, clock):
        now = _utc(2026, 5, 11, 12, 0)
        assert clock.time_to_resolve(now) == timedelta(0)


class TestBlackoutWindow:
    def test_outside_blackout(self, clock):
        # 2h before resolve
        now = _utc(2026, 5, 11, 10, 0)
        assert clock.is_in_blackout_window(now, blackout_minutes=30) is False

    def test_inside_blackout(self, clock):
        # 15min before resolve
        now = _utc(2026, 5, 11, 11, 45)
        assert clock.is_in_blackout_window(now, blackout_minutes=30) is True

    def test_exactly_at_blackout_edge(self, clock):
        # Exactly 30min before — boundary is inclusive on the cap
        now = _utc(2026, 5, 11, 11, 30)
        assert clock.is_in_blackout_window(now, blackout_minutes=30) is True

    def test_at_resolve_not_in_blackout(self, clock):
        # ttr == 0, blackout is strictly > 0
        now = _utc(2026, 5, 11, 12, 0)
        assert clock.is_in_blackout_window(now, blackout_minutes=30) is False

    def test_zero_blackout_disables_window(self, clock):
        now = _utc(2026, 5, 11, 11, 59)
        assert clock.is_in_blackout_window(now, blackout_minutes=0) is False


class TestSnapshotAndBuilder:
    def test_snapshot_dict_keys(self, clock):
        now = _utc(2026, 5, 11, 8, 0)
        snap = clock.snapshot(now).as_dict()
        assert snap["resolve_anchor_utc"].startswith("2026-05-11T12:00:00")
        assert snap["previous_resolve_utc"].startswith("2026-05-10T12:00:00")
        assert snap["next_resolve_utc"].startswith("2026-05-12T12:00:00")
        assert snap["time_to_resolve_seconds"] == 4 * 3600
        assert snap["is_in_blackout"] is False
        assert snap["valid_for_market"] is True

    def test_blackout_invalidates_market(self, clock):
        now = _utc(2026, 5, 11, 11, 50)
        snap = clock.snapshot(now).as_dict()
        assert snap["is_in_blackout"] is True
        assert snap["valid_for_market"] is False

    def test_build_time_anchor_returns_dict(self):
        d = build_time_anchor()
        assert "resolve_anchor_utc" in d
        assert "valid_for_market" in d


def test_resolve_hour_constant_is_noon():
    assert POLYMARKET_DAILY_RESOLVE_UTC_HOUR == 12


def test_default_blackout_is_30_minutes():
    assert DEFAULT_BLACKOUT_MINUTES == 30
