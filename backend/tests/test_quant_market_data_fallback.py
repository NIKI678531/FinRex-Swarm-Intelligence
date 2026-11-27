"""Tests for quant market-data provider fallbacks."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.quant.data import market_data


class TestQuantMarketDataFallback(unittest.TestCase):
    def test_3033_hk_uses_akshare_when_yfinance_empty(self):
        import pandas as pd

        rows = pd.DataFrame(
            {
                "open": [10.0, 10.1, 10.2],
                "high": [10.2, 10.3, 10.4],
                "low": [9.9, 10.0, 10.1],
                "close": [10.1, 10.2, 10.3],
                "volume": [1000, 1100, 1200],
            },
            index=pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"], utc=True),
        )

        original_yfinance = market_data._fetch_yfinance
        original_akshare = market_data._fetch_akshare
        original_cache_dir = market_data.config.MARKET_CACHE_DIR
        with tempfile.TemporaryDirectory() as tmp:
            market_data.config.MARKET_CACHE_DIR = Path(tmp)
            market_data._fetch_yfinance = lambda *args, **kwargs: None
            market_data._fetch_akshare = lambda *args, **kwargs: rows
            try:
                out = market_data.fetch_ohlcv("3033.HK", "2026-01-01", "2026-01-03", use_cache=False)
            finally:
                market_data._fetch_yfinance = original_yfinance
                market_data._fetch_akshare = original_akshare
                market_data.config.MARKET_CACHE_DIR = original_cache_dir

        self.assertEqual(len(out), 3)
        self.assertEqual(out.attrs["data_quality"]["data_source"], "akshare_fallback")


if __name__ == "__main__":
    unittest.main()
