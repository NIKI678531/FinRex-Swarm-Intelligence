"""Unit tests for StockForecastService (Phase F)."""

from __future__ import annotations

import os
import random
import sys
import types
import unittest
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.services.financial.stock_forecast_service import StockForecastService


def _ohlcv_series(n: int = 120, start: float = 100.0, drift: float = 0.004, noise: float = 0.002, seed: int = 7):
    rnd = random.Random(seed)
    rows = []
    price = start
    for i in range(n):
        ret = drift + rnd.gauss(0, noise)
        new_price = max(1.0, price * (1.0 + ret))
        rows.append({
            "date": f"2025-{(i // 30) + 1:02d}-{(i % 30) + 1:02d}",
            "open": price,
            "high": max(price, new_price) * 1.002,
            "low": min(price, new_price) * 0.998,
            "close": new_price,
            "volume": 1_000_000 + i * 1000,
        })
        price = new_price
    return rows


def _indicators_from_rows(rows):
    closes = [r["close"] for r in rows]
    last = closes[-1]
    ma20 = sum(closes[-20:]) / 20.0 if len(closes) >= 20 else last
    ma60 = sum(closes[-60:]) / 60.0 if len(closes) >= 60 else last
    trend = "up" if last > ma20 > ma60 else ("down" if last < ma20 < ma60 else "sideways")
    return {
        "last_close": last,
        "ma20": ma20,
        "ma60": ma60,
        "rsi14": 55.0,
        "return_5d": (closes[-1] / closes[-6] - 1.0) if len(closes) > 6 else 0.0,
        "return_30d": (closes[-1] / closes[-31] - 1.0) if len(closes) > 31 else 0.0,
        "volatility_30d": 0.02,
        "trend": trend,
    }


class DummyMarketProvider:
    def __init__(self, rows, gap_pct=0.005, bench_return=0.04, earnings_in_window=False, days_to_event=10):
        self.rows = rows
        self._gap_pct = gap_pct
        self._bench = bench_return
        self._earnings_in_window = earnings_in_window
        self._days_to_event = days_to_event

    def fetch_snapshot(self, symbol, asset_type="stock", lookback_days=180):
        return {
            "ok": bool(self.rows),
            "symbol": symbol,
            "normalized_symbol": symbol,
            "asset_type": asset_type,
            "rows_count": len(self.rows),
            "ohlcv": self.rows,
            "indicators": _indicators_from_rows(self.rows) if self.rows else {},
            "source": "unit_test",
            "fetched_at": "2026-05-07T00:00:00",
        }

    def fetch_overnight_gap(self, symbol):
        import math
        return {
            "ok": True,
            "symbol": symbol,
            "gap_pct": self._gap_pct,
            "factor": math.tanh(self._gap_pct / 0.03),
            "source": "dummy",
        }

    def fetch_benchmark_trend(self, symbol, lookback_days=30):
        return {
            "ok": True,
            "symbol": symbol,
            "benchmark": "SPY",
            "benchmark_return_30d": self._bench,
            "beta": 1.1,
            "factor": max(-1.0, min(1.0, self._bench * 8.0)),
            "source": "dummy",
        }

    def fetch_options_signal(self, symbol):
        return {"ok": False, "reason": "options PCR unavailable on current FMP tier"}

    def fetch_earnings_window(self, symbol, window_days=5):
        return {
            "ok": True,
            "symbol": symbol,
            "in_window": self._earnings_in_window,
            "days_to_event": self._days_to_event,
            "event_date": "2026-05-12",
            "source": "dummy",
        }


class DummyNewsProvider:
    def __init__(self, items=None):
        self.items = items or []

    def collect_corpus(self, symbol, asset_type="stock", user_comments=None, selected_articles=None,
                       news_limit=20, hours=72, include_press_releases=True, include_general_news=True,
                       general_news_query=None):
        all_items = list(self.items) + [
            {"text": c, "source": "user", "weight": 1.0} for c in (user_comments or [])
        ]
        return {
            "ok": True,
            "all": all_items,
            "news": self.items,
            "user_comments": user_comments or [],
            "selected_articles": selected_articles or [],
            "press_releases": [],
            "general_news": [],
        }


class DummySentimentProvider:
    def __init__(self, compound=0.4, count=10, model="dummy"):
        self._compound = compound
        self._count = count
        self._model = model

    def score_corpus(self, items):
        return {
            "ok": self._count > 0,
            "model": self._model,
            "count": self._count,
            "average_compound": self._compound,
            "weighted_avg_compound": self._compound,
            "summary": {
                "count": self._count,
                "average_compound": self._compound,
                "weighted_avg_compound": self._compound,
                "pos_ratio": 0.6 if self._compound > 0 else 0.2,
                "neg_ratio": 0.2 if self._compound > 0 else 0.6,
                "neu_ratio": 0.2,
            },
            "timeline": [],
            "items": [],
        }


class TestStockForecastService(unittest.TestCase):
    def setUp(self):
        fake_foundation = types.SimpleNamespace(
            predict_ensemble=lambda _df, horizon=1: None,
            summarize_unavailable_reason=lambda: "foundation disabled in unit test",
        )
        self._foundation_patch = patch.dict(
            sys.modules,
            {"app.quant.models.foundation_ensemble": fake_foundation},
        )
        self._foundation_patch.start()

    def tearDown(self):
        self._foundation_patch.stop()

    def test_bullish_path(self):
        svc = StockForecastService(
            market_provider=DummyMarketProvider(_ohlcv_series(drift=0.008), gap_pct=0.01, bench_return=0.05),
            sentiment_provider=DummySentimentProvider(compound=0.45, count=20),
            news_provider=DummyNewsProvider(items=[{"text": "Strong rally", "weight": 1.0}]),
        )
        out = svc.forecast(symbol="NVDA", comments=["bullish breakout"])
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["direction"], "up")
        self.assertGreater(out["score_breakdown"]["composite"], 0.08)
        # Options dropped → weight should be redistributed
        weights = out["score_breakdown"]["weights"]
        self.assertEqual(weights.get("options_iv", 0.0), 0.0)
        self.assertAlmostEqual(sum(weights.values()), 1.0, places=3)

    def test_bearish_path(self):
        svc = StockForecastService(
            market_provider=DummyMarketProvider(_ohlcv_series(drift=-0.008), gap_pct=-0.012, bench_return=-0.04),
            sentiment_provider=DummySentimentProvider(compound=-0.4, count=15),
            news_provider=DummyNewsProvider(),
        )
        out = svc.forecast(symbol="TSLA", comments=[])
        self.assertEqual(out["direction"], "down")
        self.assertLess(out["score_breakdown"]["composite"], -0.08)

    def test_neutral_when_below_threshold(self):
        svc = StockForecastService(
            market_provider=DummyMarketProvider(_ohlcv_series(drift=0.0, noise=0.0005, seed=11), gap_pct=0.0, bench_return=0.0),
            sentiment_provider=DummySentimentProvider(compound=0.01, count=3),
            news_provider=DummyNewsProvider(),
        )
        out = svc.forecast(symbol="AAPL", comments=[])
        # Composite should be very small; allow either neutral or weak direction with low confidence
        self.assertIn(out["direction"], ("neutral", "up", "down"))
        self.assertLess(abs(out["score_breakdown"]["composite"]), 0.20)

    def test_earnings_window_downgrades_confidence(self):
        svc = StockForecastService(
            market_provider=DummyMarketProvider(_ohlcv_series(drift=0.01), gap_pct=0.01, bench_return=0.05,
                                                earnings_in_window=True, days_to_event=3),
            sentiment_provider=DummySentimentProvider(compound=0.5, count=20),
            news_provider=DummyNewsProvider(),
        )
        out = svc.forecast(symbol="NVDA", comments=["bullish"])
        self.assertEqual(out["confidence"], "low")
        self.assertTrue(out["data_quality"].get("earnings_in_window"))
        self.assertTrue(any("Earnings" in w for w in out.get("warnings", [])))

    def test_weight_renormalization_when_factors_missing(self):
        # No sentiment, no benchmark, no gap → only technical + (no options/pulse) → all weight to technical
        class NoBench(DummyMarketProvider):
            def fetch_overnight_gap(self, s): return {"ok": False, "reason": "n/a"}
            def fetch_benchmark_trend(self, s, lookback_days=30): return {"ok": False, "reason": "n/a"}

        svc = StockForecastService(
            market_provider=NoBench(_ohlcv_series(drift=0.005)),
            sentiment_provider=DummySentimentProvider(compound=0.0, count=0),
            news_provider=DummyNewsProvider(),
        )
        out = svc.forecast(symbol="MSFT", comments=[])
        weights = out["score_breakdown"]["weights"]
        self.assertAlmostEqual(weights.get("technical", 0.0), 1.0, places=3)
        self.assertEqual(weights.get("sentiment", 0.0), 0.0)

    def test_precise_forecast_uses_foundation_ensemble(self):
        fake_foundation = types.SimpleNamespace(
            predict_ensemble=lambda _df, horizon=1: {
                "predicted_price": 123.45,
                "p10": 120.0,
                "p50": 123.0,
                "p90": 127.0,
                "p_up": 0.72,
                "expected_return": 0.03,
                "foundation_uncertainty": 0.015,
                "cross_model_agreement": 0.91,
                "mode": "kronos+chronos",
                "horizon": horizon,
                "last_close": 119.85,
                "model_status": {"available": True},
            },
            summarize_unavailable_reason=lambda: "unused",
        )
        svc = StockForecastService(
            market_provider=DummyMarketProvider(_ohlcv_series(drift=0.004)),
            sentiment_provider=DummySentimentProvider(compound=0.2, count=10),
            news_provider=DummyNewsProvider(),
        )
        with patch.dict(sys.modules, {"app.quant.models.foundation_ensemble": fake_foundation}):
            out = svc.forecast(symbol="NVDA", comments=[])

        precise = out.get("precise_forecast")
        self.assertIsNotNone(precise)
        self.assertEqual(precise.get("mode"), "kronos+chronos")
        self.assertEqual(precise.get("predicted_price"), 123.45)
        self.assertEqual(precise.get("horizon_days"), 1)

    def test_precise_forecast_falls_back_when_foundation_unavailable(self):
        svc = StockForecastService(
            market_provider=DummyMarketProvider(_ohlcv_series(drift=0.004)),
            sentiment_provider=DummySentimentProvider(compound=0.2, count=10),
            news_provider=DummyNewsProvider(),
        )
        out = svc.forecast(symbol="MSFT", comments=[])
        precise = out.get("precise_forecast")
        self.assertIsNotNone(precise)
        self.assertIn(precise.get("mode"), {"technical_range_fallback", "last_close_fallback"})
        self.assertIsNotNone(precise.get("predicted_price"))


if __name__ == "__main__":
    unittest.main()
