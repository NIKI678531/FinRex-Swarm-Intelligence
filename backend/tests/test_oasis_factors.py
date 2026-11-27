from __future__ import annotations

from datetime import datetime, timezone

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.historical_signals.oasis_factor_builder import OASIS_FACTOR_KEYS, build_oasis_daily_factors, neutral_oasis_factors


def test_neutral_oasis_factors_has_complete_schema():
    factors = neutral_oasis_factors()
    assert set(factors) == set(OASIS_FACTOR_KEYS)
    assert all(value == 0.0 for value in factors.values())


def test_missing_oasis_stream_is_neutral_metadata_only():
    payload = build_oasis_daily_factors(
        None,
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 10, tzinfo=timezone.utc),
    )
    assert payload["rows_by_date"] == {}
    assert payload["coverage"]["available"] is False
    assert payload["coverage"]["action_count"] == 0
