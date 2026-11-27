"""Tests for market feature engineering (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.quant.features.market_features import compute_market_features
from tests.quant._fixtures import make_synthetic_ohlcv


def test_compute_market_features_columns():
    df = make_synthetic_ohlcv(n=300)
    feat = compute_market_features(df)
    expected = {
        "ret_1", "ret_5", "ret_20", "vol_5", "vol_20", "volume_z_20",
        "ema_fast", "ema_slow", "macd", "macd_signal", "macd_hist",
        "rsi_14", "atr_14",
    }
    assert expected.issubset(set(feat.columns))
    assert len(feat) == len(df)
    # RSI is bounded after warmup
    rsi = feat["rsi_14"].dropna()
    assert ((rsi >= 0) & (rsi <= 100)).all()


def test_market_features_have_warmup_nans():
    df = make_synthetic_ohlcv(n=120)
    feat = compute_market_features(df)
    # Earliest rows must contain NaNs from rolling windows
    assert feat["vol_20"].iloc[0:5].isna().any()
    # Later rows should be filled
    assert feat["vol_20"].iloc[50:].notna().all()
