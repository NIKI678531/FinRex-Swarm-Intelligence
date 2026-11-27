"""Tests for legacy /api/backtest market-data fallbacks."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.services.historical_signals import data_loader_market


class TestBacktestMarketDataFallback(unittest.TestCase):
    def test_3033_hk_falls_back_to_akshare_when_yfinance_and_fmp_empty(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = datetime(2026, 1, 3, 23, 59, 59, tzinfo=timezone.utc)
        ak_rows = [
            {"ts": "2026-01-01T00:00:00+00:00", "open": 10.0, "high": 10.2, "low": 9.9, "close": 10.1, "volume": 1000.0},
            {"ts": "2026-01-02T00:00:00+00:00", "open": 10.1, "high": 10.3, "low": 10.0, "close": 10.2, "volume": 1100.0},
            {"ts": "2026-01-03T00:00:00+00:00", "open": 10.2, "high": 10.4, "low": 10.1, "close": 10.3, "volume": 1200.0},
        ]

        original_yf = data_loader_market._fetch_yfinance_daily
        original_fmp = data_loader_market._fetch_fmp_daily
        original_ak = data_loader_market._fetch_akshare_hk_daily
        original_cache_path = data_loader_market._cache_path
        with tempfile.TemporaryDirectory() as tmp:
            data_loader_market._fetch_yfinance_daily = lambda *args, **kwargs: []
            data_loader_market._fetch_fmp_daily = lambda *args, **kwargs: []
            data_loader_market._fetch_akshare_hk_daily = lambda *args, **kwargs: ak_rows
            data_loader_market._cache_path = lambda symbol, interval: os.path.join(tmp, f"{symbol}_{interval}.jsonl")
            try:
                rows = data_loader_market.fetch_ohlcv("3033.HK", "1d", start, end, use_cache=False)
            finally:
                data_loader_market._fetch_yfinance_daily = original_yf
                data_loader_market._fetch_fmp_daily = original_fmp
                data_loader_market._fetch_akshare_hk_daily = original_ak
                data_loader_market._cache_path = original_cache_path

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[-1]["close"], 10.3)


if __name__ == "__main__":
    unittest.main()
