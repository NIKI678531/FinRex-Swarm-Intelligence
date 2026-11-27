"""Regression tests for tz-aware date inputs in quant data paths."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.quant._fixtures import make_synthetic_ohlcv


def test_fetch_ohlcv_cache_accepts_tz_aware_bounds(monkeypatch, tmp_path):
    from app.quant import config
    from app.quant.data import market_data

    monkeypatch.setattr(config, "MARKET_CACHE_DIR", tmp_path)
    cached = make_synthetic_ohlcv(n=30, start="2024-01-01")
    cached.to_parquet(tmp_path / "BTC-USDT__1d.parquet")

    out = market_data.fetch_ohlcv(
        "BTC-USDT",
        pd.Timestamp("2024-01-05", tz="UTC"),
        pd.Timestamp("2024-01-20", tz="UTC"),
    )

    assert not out.empty
    assert out.index.min() == pd.Timestamp("2024-01-05", tz="UTC")
    assert out.index.max() == pd.Timestamp("2024-01-20", tz="UTC")


def test_fetch_akshare_accepts_tz_aware_bounds(monkeypatch):
    from app.quant.data import market_data, symbol_registry

    fake_akshare = types.SimpleNamespace(
        stock_zh_index_daily_em=lambda symbol: pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=10, freq="D"),
            "open": range(10),
            "high": range(1, 11),
            "low": range(10),
            "close": range(1, 11),
            "volume": range(100, 110),
        })
    )
    monkeypatch.setitem(sys.modules, "akshare", fake_akshare)

    out = market_data._fetch_akshare(
        symbol_registry.get("000300.SH"),
        pd.Timestamp("2024-01-03", tz="UTC"),
        pd.Timestamp("2024-01-06", tz="UTC"),
        "1d",
    )

    assert list(out["close"]) == [3, 4, 5, 6]
    assert out.index.tz is not None


def test_fetch_yfinance_normalizes_hk_etf(monkeypatch):
    from app.quant.data import market_data

    fake_yfinance = types.SimpleNamespace(
        download=lambda *args, **kwargs: pd.DataFrame({
            "Open": [10.0, 10.5],
            "High": [10.8, 10.9],
            "Low": [9.9, 10.1],
            "Close": [10.4, 10.7],
            "Volume": [1000, 1200],
        }, index=pd.date_range("2024-01-02", periods=2, freq="D"))
    )
    monkeypatch.setitem(sys.modules, "yfinance", fake_yfinance)

    out = market_data._fetch_yfinance(
        "3033.HK",
        pd.Timestamp("2024-01-02", tz="UTC"),
        pd.Timestamp("2024-01-03", tz="UTC"),
        "1d",
    )

    assert list(out.columns) == ["open", "high", "low", "close", "volume"]
    assert list(out["close"]) == [10.4, 10.7]
    assert out.index.tz is not None


def test_swarm_factors_accept_tz_aware_bounds(monkeypatch, tmp_path):
    from app.quant.features import swarm_factors

    sim_path = tmp_path / "2024-01-05"
    sim_path.mkdir()
    monkeypatch.setattr(
        swarm_factors,
        "_list_simulation_dates",
        lambda symbol, backfill_dir=None: [(pd.Timestamp("2024-01-05", tz="UTC"), sim_path)],
    )
    monkeypatch.setattr(
        swarm_factors,
        "_extract_one",
        lambda path, sim_ts=None: {"sentiment_mean": 0.5, "bull_ratio": 0.75, "event_intensity": 3.0},
    )

    out = swarm_factors.compute_swarm_factors(
        "BTC-USDT",
        pd.Timestamp("2024-01-01", tz="UTC"),
        pd.Timestamp("2024-01-10", tz="UTC"),
    )

    assert not out.empty
    assert set(swarm_factors.SWARM_FACTORS).issubset(out.columns)
    assert out.index.tz is not None
