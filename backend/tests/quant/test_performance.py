"""Tests for performance metrics (Sharpe, IC, drawdown)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.quant.backtest.performance import compute_performance, compute_ic


def test_compute_performance_empty():
    out = compute_performance(pd.Series(dtype=float))
    assert out["n_periods"] == 0
    assert out["sharpe"] == 0.0


def test_compute_performance_positive_drift():
    rng = np.random.default_rng(0)
    r = pd.Series(rng.normal(0.001, 0.01, 500))
    out = compute_performance(r)
    assert out["n_periods"] == 500
    assert out["sharpe"] > 0
    assert out["ann_vol"] > 0
    assert -1.0 <= out["max_drawdown"] <= 0.0
    assert 0.0 <= out["hit_ratio"] <= 1.0


def test_compute_performance_alpha_beta_against_benchmark():
    strategy = pd.Series([0.01, 0.02, -0.005, 0.015])
    benchmark = pd.Series([0.005, 0.01, -0.002, 0.006])

    out = compute_performance(strategy, benchmark_returns=benchmark)

    assert out["alpha"] is not None
    assert out["beta"] is not None
    assert out["alpha"] > 0
    assert out["beta"] > 0


def test_compute_ic_aligned_signal():
    rng = np.random.default_rng(1)
    fwd = pd.Series(rng.normal(0, 0.02, 300))
    # signal = fwd + noise → IC should be > 0
    sig = fwd + pd.Series(rng.normal(0, 0.005, 300))
    out = compute_ic(sig, fwd)
    assert out["n"] > 0
    assert out["ic_mean"] > 0.3


def test_compute_ic_empty():
    out = compute_ic(pd.Series(dtype=float), pd.Series(dtype=float))
    assert out["n"] == 0
