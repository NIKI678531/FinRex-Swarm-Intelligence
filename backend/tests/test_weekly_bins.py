"""Unit tests for weekly bins builder and helpers."""

from __future__ import annotations

from datetime import datetime, timezone

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.validation.weekly_bins import (
    DEFAULT_OFFSETS, assign_bin, build_weekly_bins, current_week_anchors, cycle_id,
)


def test_build_weekly_bins_default_count():
    bins = build_weekly_bins(100_000.0)
    # 1 tail-low + 2 mid-low + 1 central + 2 mid-high + 1 tail-high = 7
    assert len(bins) == 7
    assert bins[0]["low"] is None
    assert bins[-1]["high"] is None
    # central bin straddles spot
    central = [b for b in bins if b["low"] is not None and b["high"] is not None and b["low"] < 100_000 < b["high"]]
    assert len(central) == 1


def test_build_weekly_bins_indexes_contiguous():
    bins = build_weekly_bins(50_000.0)
    for i, b in enumerate(bins):
        assert b["index"] == i


def test_assign_bin_central_spot():
    bins = build_weekly_bins(100.0)
    assert assign_bin(100.0, bins) is not None
    # Far-low → first bin
    assert assign_bin(1.0, bins) == 0
    # Far-high → last bin
    assert assign_bin(10_000.0, bins) == len(bins) - 1


def test_assign_bin_edges_inclusive_lower():
    bins = build_weekly_bins(100.0)
    # Verify that a price equal to a bin's low edge belongs to that bin.
    second = bins[1]
    if second["low"] is not None:
        assert assign_bin(second["low"], bins) == second["index"]


def test_cycle_id_format():
    anchors = current_week_anchors(datetime(2026, 5, 13, tzinfo=timezone.utc))
    assert anchors["anchor"].weekday() == 0  # Monday
    cid = cycle_id(anchors["anchor"])
    assert cid.startswith("2026-W")
    assert len(cid) == 8


def test_current_week_anchors_span_seven_days():
    anchors = current_week_anchors(datetime(2026, 5, 13, 18, 30, tzinfo=timezone.utc))
    delta = anchors["resolve"] - anchors["anchor"]
    # Sunday 23:59:59 minus Monday 00:00:00 ≈ 6 days 23h 59m 59s
    assert 6 * 86400 + 23 * 3600 <= delta.total_seconds() < 7 * 86400
