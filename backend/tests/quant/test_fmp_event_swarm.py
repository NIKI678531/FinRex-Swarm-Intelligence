"""Tests for FMP-backed Swarm factor construction."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_fmp_endpoint_does_not_duplicate_stable(monkeypatch):
    from app.services.historical_signals import data_loader_fmp

    monkeypatch.setattr(data_loader_fmp.Config, "FMP_BASE_URL", "https://financialmodelingprep.com/stable")

    assert data_loader_fmp._endpoint_url("news/stock") == "https://financialmodelingprep.com/stable/news/stock"
    assert data_loader_fmp._endpoint_url("stable/news/stock") == "https://financialmodelingprep.com/stable/news/stock"


def test_fmp_symbol_variants_cover_crypto_and_stock():
    from app.services.historical_signals import data_loader_fmp

    assert "BTCUSD" in data_loader_fmp._symbol_variants("BTC-USDT")
    assert "AAPL" in data_loader_fmp._symbol_variants("AAPL")
    assert "03033.HK" in data_loader_fmp._symbol_variants("3033.HK")
    assert "SH000300" in data_loader_fmp._symbol_variants("000300.SH")


def test_fmp_endpoint_specs_route_crypto_and_stock_news():
    from app.services.historical_signals import data_loader_fmp

    crypto_endpoints = {s["endpoint"] for s in data_loader_fmp._endpoint_specs("BTC-USDT")}
    stock_specs = data_loader_fmp._endpoint_specs("3033.HK")
    stock_endpoints = {s["endpoint"] for s in stock_specs}
    stock_symbols = {s["params"]["symbols"] for s in stock_specs}

    assert crypto_endpoints == {"news/crypto"}
    assert "news/stock" in stock_endpoints
    assert "news/press-releases" in stock_endpoints
    assert {"3033", "03033", "03033.HK"}.issubset(stock_symbols)


def test_fmp_mock_news_builds_non_empty_swarm_factors(monkeypatch):
    from app.quant.features import swarm_factors
    from app.services.historical_signals import data_loader_fmp

    articles = []
    for i in range(24):
        tone = "surge rally growth" if i % 3 else "risk crash lawsuit"
        articles.append({
            "source": "fmp",
            "source_type": "press_release" if i % 5 == 0 else "crypto_news",
            "symbol": "BTCUSD",
            "raw_symbol": "BTCUSD",
            "title": f"BTC event {i}",
            "text": f"{tone} topic{i % 4}",
            "site": "Reuters" if i % 4 == 0 else "FMP",
            "url": f"https://example.test/{i}",
            "published_at": f"2024-01-{i + 1:02d}T12:00:00Z",
        })

    def fake_fetch(symbol, start, end, **kwargs):
        return {
            "items": articles,
            "coverage": {"source": "fmp", "available": True, "article_count": len(articles)},
        }

    monkeypatch.setattr(data_loader_fmp, "fetch_window_with_coverage", fake_fetch)

    df = swarm_factors.compute_swarm_factors(
        "BTC-USDT",
        pd.Timestamp("2024-01-01", tz="UTC"),
        pd.Timestamp("2024-01-31", tz="UTC"),
        source_mode="fmp_only",
    )

    assert not df.empty
    assert set(swarm_factors.SWARM_FACTORS).issubset(df.columns)
    assert df.index.tz is not None
    assert int((~df.isna().all(axis=1)).sum()) > 0
    quality = df.attrs["data_quality"]
    assert quality["fmp_rows"] > 0
    assert quality["selected_fmp_rows"] > 0


def test_oasis_only_empty_stays_empty(monkeypatch, tmp_path):
    from app.quant.features import swarm_factors

    monkeypatch.setattr(swarm_factors, "_list_simulation_dates", lambda symbol, backfill_dir=None: [])

    df = swarm_factors.compute_swarm_factors(
        "BTC-USDT",
        pd.Timestamp("2024-01-01", tz="UTC"),
        pd.Timestamp("2024-01-31", tz="UTC"),
        backfill_dir=tmp_path,
        source_mode="oasis_only",
    )

    assert df.empty
    assert df.attrs["data_quality"]["oasis_rows"] == 0
    assert "missing_or_empty_oasis_stream" in df.attrs["data_quality"]["reasons"]


def test_walk_forward_fmp_swarm_produces_nonconstant_signal(monkeypatch):
    import pytest

    pytest.importorskip("lightgbm")

    from app.services.historical_signals import data_loader_fmp
    from app.quant.backtest.walk_forward import run_walk_forward
    from tests.quant._fixtures import make_synthetic_ohlcv

    articles = []
    for i in range(220):
        positive = (i // 7) % 2 == 0
        articles.append({
            "source": "fmp",
            "source_type": "crypto_news",
            "symbol": "BTCUSD",
            "raw_symbol": "BTCUSD",
            "title": f"BTC {'surge' if positive else 'crash'} {i}",
            "text": "rally growth upgrade" if positive else "risk lawsuit downgrade",
            "site": "Reuters" if i % 9 == 0 else "FMP",
            "url": f"https://example.test/wf/{i}",
            "published_at": f"2024-01-01T12:00:00Z",
        })
        day = pd.Timestamp("2024-01-01", tz="UTC") + pd.Timedelta(days=i)
        articles[-1]["published_at"] = day.isoformat()

    def fake_fetch(symbol, start, end, **kwargs):
        return {
            "items": articles,
            "coverage": {"source": "fmp", "available": True, "article_count": len(articles)},
        }

    monkeypatch.setattr(data_loader_fmp, "fetch_window_with_coverage", fake_fetch)

    df = make_synthetic_ohlcv(n=260, start="2024-01-01")
    result = run_walk_forward(
        df,
        symbol="BTC-USDT",
        horizon=5,
        train_days=90,
        test_days=30,
        step_days=30,
        swarm_source_mode="fmp_only",
    )

    assert result.signals["p_swarm"].nunique(dropna=True) > 1
    assert result.signals["signal_swarm"].abs().sum() > 0
    assert result.data_quality["swarm"]["effective_rows"] > 0
    assert result.data_quality["swarm"]["constant_signal_warning"] is False
