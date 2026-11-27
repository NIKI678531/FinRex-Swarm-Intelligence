"""Unit tests for the asset_forecast package.

Tests are pure-Python (no network) — they generate synthetic OHLCV series so
indicator/signal/risk math can be verified deterministically.

Run with:
    python -m pytest backend/tests/test_asset_forecast.py -v
or:
    python -m unittest backend.tests.test_asset_forecast
"""

from __future__ import annotations

import math
import os
import random
import sys
import unittest

# Make ``app`` importable when running this file directly.
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.services.asset_forecast import indicators as ind
from app.services.asset_forecast import risk_metrics as rm
from app.services.asset_forecast.signal_engine import (
    MIN_BARS,
    backtest_hit_rate,
    compute_signals,
)


def _series_uptrend(n: int = 200, start: float = 100.0, drift: float = 0.004,
                    noise: float = 0.005, seed: int = 42):
    """Geometric-ish uptrend OHLCV with controllable drift/noise."""
    rnd = random.Random(seed)
    rows = []
    price = start
    for i in range(n):
        ret = drift + rnd.gauss(0, noise)
        new_price = max(0.5, price * (1.0 + ret))
        high = max(price, new_price) * (1 + abs(rnd.gauss(0, noise / 2)))
        low = min(price, new_price) * (1 - abs(rnd.gauss(0, noise / 2)))
        rows.append({
            "date": f"2025-{(i // 30) + 1:02d}-{(i % 30) + 1:02d}",
            "open": price,
            "high": high,
            "low": low,
            "close": new_price,
            "volume": 1_000_000,
        })
        price = new_price
    return rows


def _series_downtrend(n: int = 200, **kw):
    return _series_uptrend(n=n, drift=-0.004, **kw)


def _series_flat(n: int = 200, **kw):
    return _series_uptrend(n=n, drift=0.0, **kw)


# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------

class TestIndicators(unittest.TestCase):

    def test_sma_alignment(self):
        closes = list(range(1, 51))   # 1..50
        out = ind.sma(closes, 10)
        self.assertEqual(len(out), len(closes))
        # First 9 entries should be None (warmup)
        self.assertTrue(all(v is None for v in out[:9]))
        # SMA at index 9 = mean(1..10) = 5.5
        self.assertAlmostEqual(out[9], 5.5, places=6)
        # SMA at last index = mean(41..50) = 45.5
        self.assertAlmostEqual(out[-1], 45.5, places=6)

    def test_ema_alignment_and_smoothness(self):
        closes = [10.0] * 50
        out = ind.ema(closes, 10)
        # On a flat series, EMA must converge to 10.0
        self.assertAlmostEqual(out[-1], 10.0, places=4)

    def test_rsi_bounds(self):
        rows = _series_uptrend(n=120)
        closes = [r["close"] for r in rows]
        out = ind.rsi(closes, 14)
        last_values = [v for v in out if v is not None]
        self.assertTrue(last_values)
        for v in last_values:
            self.assertGreaterEqual(v, 0.0)
            self.assertLessEqual(v, 100.0)

    def test_macd_signs_on_uptrend(self):
        rows = _series_uptrend(n=120, drift=0.01, noise=0.001)
        closes = [r["close"] for r in rows]
        pkg = ind.macd(closes, 12, 26, 9)
        # In a strong uptrend, late MACD should be > signal
        self.assertGreater(pkg["macd"][-1], pkg["signal"][-1])

    def test_bollinger_width(self):
        rows = _series_flat(n=80, noise=0.002)
        closes = [r["close"] for r in rows]
        boll = ind.bollinger(closes, 20, 2.0)
        upper = boll["upper"][-1]
        lower = boll["lower"][-1]
        mid = boll["middle"][-1]
        self.assertGreater(upper, mid)
        self.assertLess(lower, mid)

    def test_atr_positive(self):
        rows = _series_uptrend(n=80)
        out = ind.atr(
            [r["high"] for r in rows],
            [r["low"] for r in rows],
            [r["close"] for r in rows],
            14,
        )
        self.assertTrue(all(v is None or v > 0 for v in out))


# ---------------------------------------------------------------------------
# Risk
# ---------------------------------------------------------------------------

class TestRiskMetrics(unittest.TestCase):

    def test_tier_caps_and_penalties(self):
        # Caps decrease as tier risk rises
        self.assertGreater(rm.tier_cap("low"), rm.tier_cap("mid"))
        self.assertGreater(rm.tier_cap("mid"), rm.tier_cap("high"))
        self.assertGreater(rm.tier_cap("high"), rm.tier_cap("very_high"))
        # Penalties increase as tier risk rises
        self.assertLess(rm.tier_penalty("low"), rm.tier_penalty("mid"))
        self.assertLess(rm.tier_penalty("mid"), rm.tier_penalty("high"))

    def test_compute_risk_shape(self):
        rows = _series_uptrend(n=150)
        closes = [r["close"] for r in rows]
        rets = ind.daily_returns(closes)
        risk = rm.compute_risk(closes, rets)
        for k in ("ann_vol", "max_drawdown", "sharpe"):
            self.assertIn(k, risk)
        self.assertGreaterEqual(risk["ann_vol"], 0.0)
        self.assertLessEqual(risk["max_drawdown"], 0.0)


# ---------------------------------------------------------------------------
# Signal engine
# ---------------------------------------------------------------------------

class TestSignalEngine(unittest.TestCase):

    def test_insufficient_history(self):
        rows = _series_uptrend(n=MIN_BARS - 5)
        out = compute_signals(rows)
        self.assertFalse(out["ok"])
        self.assertIn("insufficient_history", out["reason"])

    def test_uptrend_is_bullish(self):
        rows = _series_uptrend(n=200, drift=0.012, noise=0.002)
        out = compute_signals(rows)
        self.assertTrue(out["ok"])
        # Should be confidently bullish
        self.assertEqual(out["direction"], "bullish")
        self.assertGreaterEqual(out["score"], 3)
        self.assertGreater(out["confidence"], 0.4)
        # Expected return central should be positive
        self.assertGreater(out["expected_return_pct"]["central"], 0)

    def test_downtrend_is_bearish(self):
        rows = _series_downtrend(n=200, noise=0.002)
        out = compute_signals(rows)
        self.assertTrue(out["ok"])
        self.assertEqual(out["direction"], "bearish")
        self.assertLessEqual(out["score"], -3)
        self.assertLess(out["expected_return_pct"]["central"], 0)

    def test_horizon_widens_band(self):
        rows = _series_uptrend(n=200, drift=0.005, noise=0.01)
        s5 = compute_signals(rows, horizon_days=5)
        s21 = compute_signals(rows, horizon_days=21)
        # Same direction, but 1-month band is strictly wider than 1-week band
        width5 = s5["expected_return_pct"]["upper"] - s5["expected_return_pct"]["lower"]
        width21 = s21["expected_return_pct"]["upper"] - s21["expected_return_pct"]["lower"]
        self.assertGreater(width21, width5)
        self.assertEqual(s5["horizon_days"], 5)
        self.assertEqual(s21["horizon_days"], 21)


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------

class TestBacktest(unittest.TestCase):

    def test_uptrend_backtest_high_bullish_hit_rate(self):
        rows = _series_uptrend(n=400, drift=0.008, noise=0.003)
        bt = backtest_hit_rate(rows, horizon_days=5)
        self.assertTrue(bt["ok"])
        self.assertGreater(bt["samples"], 100)
        # The simple rule strategy on a strong uptrend should beat 60% bullish hit
        if bt["bullish_count"] > 20:
            self.assertGreater(bt["bullish_hit_rate"], 0.55)

    def test_insufficient_history_backtest(self):
        rows = _series_uptrend(n=MIN_BARS - 1)
        bt = backtest_hit_rate(rows, horizon_days=5)
        self.assertFalse(bt["ok"])


if __name__ == "__main__":
    unittest.main()
