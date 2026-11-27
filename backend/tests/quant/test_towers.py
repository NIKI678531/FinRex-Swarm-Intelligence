"""Tests for Market & Swarm towers using synthetic data."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.quant.features.market_features import compute_market_features
from app.quant.features.swarm_factors import SWARM_FACTORS
from app.quant.models.tower_market import MarketTower
from app.quant.models.tower_swarm import SwarmTower, MIN_SAMPLES_FOR_GBM
from tests.quant._fixtures import make_synthetic_ohlcv

import pytest

_HAS_LGB = True
try:
    import lightgbm  # noqa: F401
except Exception:
    _HAS_LGB = False


@pytest.mark.skipif(not _HAS_LGB, reason="lightgbm not installed")
def test_market_tower_fit_predict():
    df = make_synthetic_ohlcv(n=400)
    feat = compute_market_features(df).dropna()
    close = df["close"].loc[feat.index]

    tower = MarketTower().fit(feat, close, horizon=5)
    proba = tower.predict_proba(feat)
    assert len(proba) == len(feat)
    assert proba.between(0.0, 1.0).all()


def test_swarm_tower_rule_based_fallback_small_sample():
    """With <MIN_SAMPLES_FOR_GBM rows the swarm tower must use rule-based fallback."""
    rng = np.random.default_rng(0)
    n = 50  # well below MIN_SAMPLES_FOR_GBM
    idx = pd.date_range("2024-01-01", periods=n, freq="1D", tz="UTC")
    features = pd.DataFrame(rng.normal(0, 1, size=(n, len(SWARM_FACTORS))),
                            index=idx, columns=SWARM_FACTORS)
    close = pd.Series(100 + rng.normal(0, 1, n).cumsum(), index=idx)

    tower = SwarmTower().fit(features, close, horizon=5)
    assert tower.model is None  # fallback path
    assert tower.rule_weights is not None
    proba = tower.predict_proba(features)
    assert len(proba) == n
    assert ((proba >= 0.0) & (proba <= 1.0)).all()


@pytest.mark.skipif(not _HAS_LGB, reason="lightgbm not installed")
def test_swarm_tower_uses_gbm_with_enough_samples():
    rng = np.random.default_rng(1)
    n = MIN_SAMPLES_FOR_GBM + 100
    idx = pd.date_range("2020-01-01", periods=n, freq="1D", tz="UTC")
    features = pd.DataFrame(rng.normal(0, 1, size=(n, len(SWARM_FACTORS))),
                            index=idx, columns=SWARM_FACTORS)
    # Make close mildly correlated with feature[0] so labels are learnable
    drift = features.iloc[:, 0].cumsum() * 0.01
    close = pd.Series(100.0 + drift.values + rng.normal(0, 0.5, n).cumsum() * 0.01, index=idx)

    tower = SwarmTower().fit(features, close, horizon=5)
    # GBM path should be active
    assert tower.model is not None
    proba = tower.predict_proba(features)
    assert proba.between(0.0, 1.0).all()
