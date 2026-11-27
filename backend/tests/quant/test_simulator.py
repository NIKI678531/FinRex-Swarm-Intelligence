"""Tests for the vectorbt-style simulator (self-contained)."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.quant.backtest.vectorbt_runner import simulate
from tests.quant._fixtures import make_synthetic_ohlcv


def _series(values):
    idx = pd.date_range("2026-01-01", periods=len(values), freq="1D", tz="UTC")
    return pd.Series(values, index=idx)


def test_simulate_emits_equity_curve_and_trades():
    df = make_synthetic_ohlcv(n=200)
    close = df["close"]
    signal = pd.Series(0.0, index=close.index)
    signal.iloc[10:60] = 1.0
    signal.iloc[80:120] = -1.0

    out = simulate(close, signal, initial_cash=10000.0)

    assert "equity_curve" in out and "trades" in out and "summary" in out
    assert len(out["equity_curve"]) == len(close)
    kinds = {t["kind"] for t in out["trades"]}
    assert "entry" in kinds
    first = out["equity_curve"][0]
    assert {"ts", "cash", "value", "position_side", "position_units"}.issubset(first.keys())


def test_simulate_flat_signal_no_trades():
    df = make_synthetic_ohlcv(n=80)
    close = df["close"]
    signal = pd.Series(0.0, index=close.index)

    out = simulate(close, signal, initial_cash=5000.0)

    assert out["trades"] == []
    values = [p["value"] for p in out["equity_curve"]]
    assert all(abs(v - 5000.0) < 1e-6 for v in values)
    assert {p["position_side"] for p in out["equity_curve"]} == {"flat"}


def test_simulate_long_cash_accounting():
    close = _series([100.0, 110.0, 120.0])
    signal = _series([1.0, 1.0, 0.0])

    out = simulate(close, signal, initial_cash=10000.0, fee_bps=0.0)

    assert out["equity_curve"][0]["position_side"] == "long"
    assert out["equity_curve"][0]["cash"] == pytest.approx(500.0)
    assert out["equity_curve"][1]["value"] == pytest.approx(10950.0)
    assert out["equity_curve"][-1]["value"] == pytest.approx(11900.0)
    closed = [t for t in out["trades"] if t["kind"] != "entry"]
    assert len(closed) == 1
    assert closed[0]["pnl"] == pytest.approx(1900.0)


def test_simulate_short_cash_accounting():
    close = _series([100.0, 90.0, 80.0])
    signal = _series([-1.0, -1.0, 0.0])

    out = simulate(close, signal, initial_cash=10000.0, fee_bps=0.0)

    assert out["equity_curve"][0]["position_side"] == "short"
    assert out["equity_curve"][0]["cash"] == pytest.approx(19500.0)
    assert out["equity_curve"][1]["value"] == pytest.approx(10950.0)
    assert out["equity_curve"][-1]["value"] == pytest.approx(11900.0)
    closed = [t for t in out["trades"] if t["kind"] != "entry"]
    assert len(closed) == 1
    assert closed[0]["pnl"] == pytest.approx(1900.0)
    assert min(p["value"] for p in out["equity_curve"]) > 0


def test_simulate_flip_long_to_short_without_negative_equity_artifact():
    close = _series([100.0, 110.0, 90.0, 95.0])
    signal = _series([1.0, -1.0, -1.0, 0.0])

    out = simulate(close, signal, initial_cash=10000.0, fee_bps=0.0)

    entries = [t for t in out["trades"] if t["kind"] == "entry"]
    closed = [t for t in out["trades"] if t["kind"] != "entry"]
    assert [t["side"] for t in entries] == ["buy", "sell"]
    assert len(closed) == 2
    assert closed[0]["pnl"] == pytest.approx(950.0)
    assert closed[1]["pnl"] > 0
    assert out["equity_curve"][-1]["value"] > 10000.0
    assert min(p["value"] for p in out["equity_curve"]) > 0
