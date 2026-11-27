"""Unit tests for the structured crypto forecast service."""

from __future__ import annotations

import os
import random
import sys
import unittest
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.services.financial.crypto_forecast_service import CryptoForecastService


def _series(n: int = 200, start: float = 100.0, drift: float = 0.004, noise: float = 0.002, seed: int = 7):
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


class DummyMarketProvider:
    def __init__(self, rows):
        self.rows = rows

    def fetch_market(self, symbol="BTC", interval="1d", limit=180, ttl_minutes=10, use_cache=True):
        return {
            "ok": bool(self.rows),
            "symbol": symbol,
            "pair": f"{symbol}USDT",
            "quote": "USDT",
            "source": "unit_test",
            "fetched_at": "2026-05-07T00:00:00",
            "rows_count": len(self.rows),
            "ohlcv": self.rows,
            "ticker": {"ok": bool(self.rows), "last_price": self.rows[-1]["close"] if self.rows else None},
            "derivatives": {"ok": False, "funding": [], "open_interest": None},
            "warnings": [],
        }


class DummyNewsProvider:
    @staticmethod
    def fetch_news(symbol, asset_type="crypto", limit=20):
        return {"ok": False, "items": [], "source": "none", "error": "disabled in unit test"}


class TestCryptoForecastService(unittest.TestCase):
    def test_bullish_market_and_comments(self):
        service = CryptoForecastService(
            market_provider=DummyMarketProvider(_series(drift=0.012)),
            news_provider=DummyNewsProvider(),
        )
        out = service.forecast(
            symbol="BTC",
            comments=["BTC looks bullish breakout rally strong buy long"],
            include_news=False,
        )
        self.assertEqual(out["direction"], "bullish")
        self.assertGreater(out["probability"], 0.5)
        self.assertTrue(out["data_quality"]["market"])
        self.assertGreater(out["data_quality"]["sentiment_count"], 0)

    def test_bearish_market(self):
        service = CryptoForecastService(
            market_provider=DummyMarketProvider(_series(drift=-0.010)),
            news_provider=DummyNewsProvider(),
        )
        out = service.forecast(symbol="BTC", comments=[], include_news=False)
        self.assertEqual(out["direction"], "bearish")
        self.assertLess(out["probability"], 0.5)
        self.assertTrue(out["data_quality"]["market"])

    def test_no_comments_still_uses_market(self):
        service = CryptoForecastService(
            market_provider=DummyMarketProvider(_series(drift=0.010)),
            news_provider=DummyNewsProvider(),
        )
        out = service.forecast(symbol="ETH", comments=[], include_news=False)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["direction"], "bullish")
        self.assertFalse(out["data_quality"]["user_comments"])

    def test_insufficient_without_market_or_sentiment(self):
        service = CryptoForecastService(
            market_provider=DummyMarketProvider([]),
            news_provider=DummyNewsProvider(),
        )
        out = service.forecast(symbol="SOL", comments=[], include_news=False)
        self.assertEqual(out["status"], "insufficient_data")
        self.assertEqual(out["direction"], "neutral")
        self.assertEqual(out["probability"], 0.5)

    def test_precise_forecast_falls_back_when_foundation_unavailable(self):
        service = CryptoForecastService(
            market_provider=DummyMarketProvider(_series(drift=0.006)),
            news_provider=DummyNewsProvider(),
        )
        real_import = __import__

        def guarded_import(name, *args, **kwargs):
            if name.endswith("quant.models.foundation_ensemble"):
                raise ImportError("foundation disabled in unit test")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=guarded_import):
            out = service.forecast(symbol="BTC", comments=[], include_news=False)
        precise = out.get("precise_forecast")
        self.assertIsNotNone(precise)
        self.assertIn(precise.get("mode"), {"technical_range_fallback", "last_close_fallback"})
        self.assertIsNotNone(precise.get("predicted_price"))


if __name__ == "__main__":
    unittest.main()
