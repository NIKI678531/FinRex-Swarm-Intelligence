"""End-to-end pipeline smoke test with mocked data fetcher and OASIS."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.quant._fixtures import make_synthetic_ohlcv


def test_run_backtest_smoke(monkeypatch, tmp_path):
    pytest.importorskip("lightgbm")
    from app.quant import config, pipeline
    from app.quant.data import market_data
    from app.quant.backtest import price_point_calibrated_ml as ppml
    from app.quant.backtest import walk_forward as wf
    from app.quant.features.swarm_factors import SWARM_FACTORS

    monkeypatch.setattr(config, "BACKTEST_RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(config, "PRICE_CALIBRATION_DIR", tmp_path / "price_calibration")

    def fake_fetch(symbol, start, end, freq="1d", use_cache=True):
        return make_synthetic_ohlcv(n=600)

    def fake_swarm(symbol, start, end, backfill_dir=None, **kwargs):
        idx = pd.DatetimeIndex([], tz="UTC", name="ts")
        return pd.DataFrame(columns=SWARM_FACTORS, index=idx)

    def fake_foundation(hist, horizon=5, **_kwargs):
        close = hist["close"].astype(float)
        last = float(close.iloc[-1])
        ret_5 = last / float(close.iloc[-6]) - 1.0 if len(close) > 6 else 0.0
        expected = 0.35 * ret_5
        band = max(0.015, abs(expected) + 0.02)
        return {
            "predicted_price": last * (1.0 + expected),
            "p10": last * (1.0 + expected - band),
            "p50": last * (1.0 + expected),
            "p90": last * (1.0 + expected + band),
            "p_up": 0.5 + max(-0.35, min(0.35, expected * 10)),
            "expected_return": expected,
            "foundation_uncertainty": band,
            "cross_model_agreement": 0.9,
            "mode": "kronos+chronos",
            "horizon": horizon,
            "last_close": last,
        }, None

    monkeypatch.setattr(market_data, "fetch_ohlcv", fake_fetch)
    monkeypatch.setattr(wf, "compute_swarm_factors", fake_swarm)
    monkeypatch.setattr(ppml, "compute_swarm_factors", fake_swarm)
    monkeypatch.setattr(ppml, "foundation_or_fallback_forecast", fake_foundation)
    monkeypatch.setattr(config, "WF_TRAIN_DAYS", 240)
    monkeypatch.setattr(config, "WF_TEST_DAYS", 60)
    monkeypatch.setattr(config, "WF_STEP_DAYS", 60)
    monkeypatch.setattr(config, "PRICE_ML_FOUNDATION_MODE", "full")
    monkeypatch.setattr(config, "PRICE_ML_MAX_FOUNDATION_CALLS", 999)

    result = pipeline.run_backtest(
        symbol="BTC-USDT",
        start="2020-01-01",
        end="2022-01-01",
        horizon=5,
        initial_cash=10000.0,
    )

    assert "run_id" in result
    assert "equity_curve" in result and len(result["equity_curve"]) > 0
    assert "chart_points" in result and len(result["chart_points"]) == len(result["equity_curve"])
    assert "performance" in result
    assert result["config"]["model_family"] == "price_point_calibrated_ml"
    for key in ("market_only", "swarm_only", "hybrid", "ic"):
        assert key in result["performance"]
    assert "swarm" in result["data_quality"]
    assert "price_forecast_model" in result["data_quality"]

    chart_row = result["chart_points"][-1]
    required = {
        "ts", "open", "high", "low", "close", "volume", "cash", "value",
        "position_side", "position_units", "p_meta", "signal_hybrid",
        "ema_9", "ema_12", "ema_26", "kdj_k", "kdj_d", "kdj_j",
        "highest_9", "lowest_9", "macd", "macd_signal", "macd_hist",
    }
    assert required.issubset(chart_row.keys())
    assert any(p["ema_9"] is not None for p in result["chart_points"])
    assert any(p["kdj_k"] is not None for p in result["chart_points"])
    assert any(p["macd_hist"] is not None for p in result["chart_points"])

    run_dir = (tmp_path / "runs") / result["run_id"]
    assert (run_dir / "result.json").exists()

    runs = pipeline.list_runs()
    assert any(r.get("run_id") == result["run_id"] for r in runs)
    doc = pipeline.get_run(result["run_id"])
    assert doc["run_id"] == result["run_id"]
    assert "chart_points" in doc
    assert pipeline.delete_run(result["run_id"]) is True
