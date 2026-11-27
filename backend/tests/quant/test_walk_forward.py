"""Smoke test: walk-forward end-to-end with synthetic data (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.quant.backtest.walk_forward import run_walk_forward
from tests.quant._fixtures import make_synthetic_ohlcv

import pytest
pytest.importorskip("lightgbm")


def test_walk_forward_single_shot_short_history(monkeypatch):
    """Short history triggers _single_shot_fit branch."""
    # Patch compute_swarm_factors to return empty (no OASIS data)
    from app.quant.backtest import walk_forward as wf
    from app.quant.features.swarm_factors import SWARM_FACTORS

    def fake_swarm(symbol, start, end, backfill_dir=None, **kwargs):
        idx = pd.DatetimeIndex([], tz="UTC", name="ts")
        return pd.DataFrame(columns=SWARM_FACTORS, index=idx)

    monkeypatch.setattr(wf, "compute_swarm_factors", fake_swarm)

    df = make_synthetic_ohlcv(n=150)  # below train+test threshold
    result = run_walk_forward(df, symbol="SYNTH-TEST", horizon=5)
    assert hasattr(result, "signals")
    assert "p_market" in result.signals.columns
    assert "signal_hybrid" in result.signals.columns
    assert "n_periods" in result.perf_hybrid


def test_walk_forward_full_pipeline(monkeypatch):
    """Enough history for the rolling WF loop to execute."""
    from app.quant.backtest import walk_forward as wf
    from app.quant.features.swarm_factors import SWARM_FACTORS

    def fake_swarm(symbol, start, end, backfill_dir=None, **kwargs):
        idx = pd.DatetimeIndex([], tz="UTC", name="ts")
        return pd.DataFrame(columns=SWARM_FACTORS, index=idx)

    monkeypatch.setattr(wf, "compute_swarm_factors", fake_swarm)

    # Use shorter WF windows so test stays fast
    df = make_synthetic_ohlcv(n=900)
    result = run_walk_forward(
        df, symbol="SYNTH-TEST", horizon=5,
        train_days=240, test_days=60, step_days=60,
    )
    sig = result.signals
    assert {"p_market", "p_swarm", "p_meta",
            "signal_market", "signal_swarm", "signal_hybrid"}.issubset(sig.columns)
    assert len(sig) > 0
    for perf in (result.perf_market, result.perf_swarm, result.perf_hybrid):
        assert "sharpe" in perf and "max_drawdown" in perf
    assert "ic_mean" in result.ic
    assert "swarm" in result.data_quality
