from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.quant._fixtures import make_synthetic_ohlcv


def test_price_point_calibrated_ml_backtest_persists_artifact(monkeypatch, tmp_path):
    from app.quant import config
    from app.quant.backtest import price_point_calibrated_ml as ppml
    from app.quant.features.swarm_factors import SWARM_FACTORS
    from app.quant.models.price_point_calibrator import apply_latest_calibration, latest_artifact_path

    monkeypatch.setattr(config, "PRICE_CALIBRATION_DIR", tmp_path / "price_calibration")

    def fake_swarm(symbol, start, end, backfill_dir=None, **kwargs):
        idx = pd.DatetimeIndex([], tz="UTC", name="ts")
        frame = pd.DataFrame(columns=SWARM_FACTORS, index=idx)
        frame.attrs["data_quality"] = {"source_mode": "unit", "effective_rows": 0, "coverage_ratio": 0.0}
        return frame

    def fake_foundation(hist, horizon=3, **_kwargs):
        close = hist["close"].astype(float)
        last = float(close.iloc[-1])
        ret_5 = last / float(close.iloc[-6]) - 1.0 if len(close) > 6 else 0.0
        expected = 0.4 * ret_5 - 0.001
        band = max(0.015, abs(expected) + 0.02)
        return {
            "predicted_price": last * (1.0 + expected),
            "p10": last * (1.0 + expected - band),
            "p50": last * (1.0 + expected),
            "p90": last * (1.0 + expected + band),
            "p_up": 0.5 + max(-0.3, min(0.3, expected * 8)),
            "expected_return": expected,
            "foundation_uncertainty": band,
            "cross_model_agreement": 0.88,
            "mode": "kronos+chronos",
            "horizon": horizon,
            "last_close": last,
        }, None

    monkeypatch.setattr(ppml, "compute_swarm_factors", fake_swarm)
    monkeypatch.setattr(ppml, "foundation_or_fallback_forecast", fake_foundation)
    monkeypatch.setattr(config, "PRICE_ML_FOUNDATION_MODE", "full")
    monkeypatch.setattr(config, "PRICE_ML_MAX_FOUNDATION_CALLS", 999)

    df = make_synthetic_ohlcv(n=220)
    result = ppml.run_price_point_calibrated_ml_backtest(
        df,
        symbol="BTC-USDT",
        horizon=3,
        train_days=90,
        step_days=30,
        run_id="unit_run",
    )

    assert len(result.signals) > 0
    assert {"predicted_price", "p10", "p90", "calibrated_expected_return"}.issubset(result.signals.columns)
    quality = result.data_quality["price_forecast_model"]
    assert quality["engine"] == "price_point_calibrated_ml_v1"
    assert quality["calibration_sample_count"] > 0
    assert latest_artifact_path("BTC-USDT", 3).exists()

    raw, _reason = fake_foundation(df.tail(120), horizon=3)
    calibrated = apply_latest_calibration("BTC", 3, df.tail(120), raw)
    assert calibrated["calibration_applied"] is True
    assert calibrated["mode"] == "price_point_calibrated_ml_v1"
    assert calibrated["raw_predicted_price"] == raw["predicted_price"]


def test_price_point_calibrated_ml_skips_foundation_by_default(monkeypatch, tmp_path):
    from app.quant import config
    from app.quant.backtest import price_point_calibrated_ml as ppml
    from app.quant.features.swarm_factors import SWARM_FACTORS

    monkeypatch.setattr(config, "PRICE_CALIBRATION_DIR", tmp_path / "price_calibration")
    monkeypatch.setattr(config, "PRICE_ML_FOUNDATION_MODE", "none")
    monkeypatch.setattr(config, "PRICE_ML_MAX_FOUNDATION_CALLS", 1)

    def fake_swarm(symbol, start, end, backfill_dir=None, **kwargs):
        idx = pd.DatetimeIndex([], tz="UTC", name="ts")
        frame = pd.DataFrame(columns=SWARM_FACTORS, index=idx)
        frame.attrs["data_quality"] = {"source_mode": "unit", "effective_rows": 0, "coverage_ratio": 0.0}
        return frame

    def fail_if_foundation_called(hist, horizon=3, **kwargs):
        if kwargs.get("use_foundation"):
            raise AssertionError("foundation should not run in default interactive policy")
        from app.quant.models.price_point_calibrator import volatility_quantile_forecast

        return volatility_quantile_forecast(hist, horizon, "unit skip"), "unit skip"

    monkeypatch.setattr(ppml, "compute_swarm_factors", fake_swarm)
    monkeypatch.setattr(ppml, "foundation_or_fallback_forecast", fail_if_foundation_called)

    result = ppml.run_price_point_calibrated_ml_backtest(
        make_synthetic_ohlcv(n=180),
        symbol="BTC-USDT",
        horizon=3,
        train_days=90,
        step_days=30,
        run_id="fast_run",
    )

    quality = result.data_quality["price_forecast_model"]
    assert quality["foundation_policy"] == "none"
    assert quality["foundation_calls"] == 0
    assert quality["numerical_fallback_calls"] == len(result.signals)
