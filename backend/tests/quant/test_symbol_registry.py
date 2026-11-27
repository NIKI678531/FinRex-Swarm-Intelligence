"""Symbol registry tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.quant.data import symbol_registry


def test_default_symbols_present():
    syms = {s.symbol for s in symbol_registry.list_symbols()}
    for required in ("BTC-USDT", "ETH-USDT", "3033.HK", "AAPL", "000300.SH"):
        assert required in syms


def test_get_and_exists():
    assert symbol_registry.exists("BTC-USDT") is True
    assert symbol_registry.exists("NOPE-XXX") is False
    meta = symbol_registry.get("AAPL")
    assert meta.asset_class == "us_stock"
    assert meta.data_source in {"ccxt", "akshare", "yfinance"}


def test_to_dict_roundtrip():
    meta = symbol_registry.get("3033.HK")
    d = meta.to_dict()
    assert d["symbol"] == "3033.HK"
    assert "data_source" in d


def test_hk_3033_uses_yfinance_for_market_data():
    meta = symbol_registry.get("3033.HK")
    assert meta.data_source == "yfinance"
    assert meta.provider_symbol == "3033.HK"
    assert meta.news_source == "fmp"
