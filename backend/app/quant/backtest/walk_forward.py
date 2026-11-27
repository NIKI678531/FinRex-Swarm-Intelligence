"""Purged Walk-Forward training driver.

For each step we:
  1. fit Market Tower + Swarm Tower on the train window
  2. predict OOF probabilities on the test window
  3. fit Meta-Model on accumulated OOF probabilities (only past data)
  4. emit signals for the test window
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .. import config
from ..features.market_features import compute_market_features
from ..features.swarm_factors import compute_swarm_factors, SWARM_FACTORS
from ..models.tower_market import MarketTower
from ..models.tower_swarm import SwarmTower
from ..models.meta_model import MetaModel
from . import performance as perf


@dataclass
class WalkForwardResult:
    signals: object       # pd.DataFrame: p_market, p_swarm, p_meta, signal_*
    perf_market: dict
    perf_swarm: dict
    perf_hybrid: dict
    ic: dict
    data_quality: dict


def run_walk_forward(
    ohlcv,
    symbol: str,
    horizon: int = 5,
    train_days: Optional[int] = None,
    test_days: Optional[int] = None,
    step_days: Optional[int] = None,
    swarm_source_mode: str = "auto",
    oasis_simulation_id: Optional[str] = None,
    sentiment_sources: Optional[list[str]] = None,
) -> WalkForwardResult:
    import pandas as pd

    train_days = train_days or config.WF_TRAIN_DAYS
    test_days = test_days or config.WF_TEST_DAYS
    step_days = step_days or config.WF_STEP_DAYS

    market_feats = compute_market_features(ohlcv)
    swarm = compute_swarm_factors(
        symbol,
        ohlcv.index.min(),
        ohlcv.index.max(),
        source_mode=swarm_source_mode,
        oasis_simulation_id=oasis_simulation_id,
        sentiment_sources=sentiment_sources,
    )
    swarm_quality = dict(swarm.attrs.get("data_quality") or {})
    swarm = swarm.reindex(ohlcv.index).ffill(limit=config.SWARM_FFILL_LIMIT)
    swarm_quality["effective_rows"] = int((~swarm.isna().all(axis=1)).sum()) if len(swarm) else 0
    swarm_quality["coverage_ratio"] = (
        swarm_quality["effective_rows"] / len(swarm) if len(swarm) else 0.0
    )

    close = ohlcv["close"]
    fwd_ret = close.shift(-horizon) / close - 1.0

    all_idx = ohlcv.index
    if len(all_idx) < train_days + test_days + 5:
        # Not enough history: produce a single end-to-end fit so we at least
        # have something to display in the UI.
        return _single_shot_fit(market_feats, swarm, ohlcv, close, fwd_ret, horizon, swarm_quality)

    out_rows = []
    start_i = train_days
    while start_i + test_days <= len(all_idx):
        train_idx = all_idx[start_i - train_days:start_i]
        test_idx = all_idx[start_i:start_i + test_days]

        mt = MarketTower().fit(market_feats.loc[train_idx], close.loc[train_idx], horizon=horizon)
        st = SwarmTower().fit(swarm.loc[train_idx], close.loc[train_idx], horizon=horizon)

        p_m = mt.predict_proba(market_feats.loc[test_idx])
        p_s = st.predict_proba(swarm.loc[test_idx])

        rows = pd.DataFrame({
            "p_market": p_m,
            "p_swarm": p_s,
            "vol_5d": market_feats["vol_5"].loc[test_idx],
            "vol_20d": market_feats["vol_20"].loc[test_idx],
            "volume_z": market_feats["volume_z_20"].loc[test_idx],
            "event_flag": swarm.get("event_intensity", pd.Series(0.0, index=test_idx)).reindex(test_idx).fillna(0.0),
        }, index=test_idx)
        out_rows.append(rows)
        start_i += step_days

    if not out_rows:
        return _single_shot_fit(market_feats, swarm, ohlcv, close, fwd_ret, horizon, swarm_quality)

    oof = pd.concat(out_rows).sort_index()
    # Fit Meta on the first half of OOF, evaluate on the second half
    cut = len(oof) // 2
    meta_train = oof.iloc[:cut]
    meta_test = oof.iloc[cut:]
    direction = (fwd_ret.loc[meta_train.index] > 0).astype(float)
    meta = MetaModel(kind="logreg").fit(meta_train, direction)
    p_meta_test = meta.predict_proba(meta_test)
    p_meta = pd.concat([
        pd.Series(0.5, index=meta_train.index),
        p_meta_test,
    ])
    oof["p_meta"] = p_meta

    # Strategy returns: take T+1 to T+horizon forward window return scaled by signal
    def sig(p):
        return (p - 0.5) * 2  # -1..+1
    oof["signal_market"] = sig(oof["p_market"]).clip(-1, 1)
    oof["signal_swarm"] = sig(oof["p_swarm"]).clip(-1, 1)
    oof["signal_hybrid"] = sig(oof["p_meta"]).clip(-1, 1)

    daily_ret = close.pct_change().shift(-1)  # T+1 return
    oof["ret_next"] = daily_ret.reindex(oof.index)

    perf_m = perf.compute_performance(oof["signal_market"] * oof["ret_next"], benchmark_returns=oof["ret_next"])
    perf_s = perf.compute_performance(oof["signal_swarm"] * oof["ret_next"], benchmark_returns=oof["ret_next"])
    perf_h = perf.compute_performance(oof["signal_hybrid"] * oof["ret_next"], benchmark_returns=oof["ret_next"])
    ic = perf.compute_ic(oof["p_meta"], fwd_ret.reindex(oof.index))
    data_quality = _finalize_data_quality(swarm_quality, oof)

    return WalkForwardResult(
        signals=oof, perf_market=perf_m, perf_swarm=perf_s,
        perf_hybrid=perf_h, ic=ic, data_quality=data_quality,
    )


def _single_shot_fit(market_feats, swarm, ohlcv, close, fwd_ret, horizon, swarm_quality=None):
    import pandas as pd
    idx = ohlcv.index
    n = len(idx)
    cut = max(10, int(n * 0.6))
    train_idx = idx[:cut]
    test_idx = idx[cut:]

    mt = MarketTower().fit(market_feats.loc[train_idx], close.loc[train_idx], horizon=horizon)
    st = SwarmTower().fit(swarm.loc[train_idx], close.loc[train_idx], horizon=horizon)

    p_m = mt.predict_proba(market_feats.loc[test_idx])
    p_s = st.predict_proba(swarm.loc[test_idx])
    oof = pd.DataFrame({
        "p_market": p_m, "p_swarm": p_s,
        "vol_5d": market_feats["vol_5"].loc[test_idx],
        "vol_20d": market_feats["vol_20"].loc[test_idx],
        "volume_z": market_feats["volume_z_20"].loc[test_idx],
        "event_flag": swarm.get("event_intensity", pd.Series(0.0, index=test_idx)).reindex(test_idx).fillna(0.0),
    }, index=test_idx)
    oof["p_meta"] = (oof["p_market"] + oof["p_swarm"]) / 2.0
    oof["signal_market"] = (oof["p_market"] - 0.5) * 2
    oof["signal_swarm"] = (oof["p_swarm"] - 0.5) * 2
    oof["signal_hybrid"] = (oof["p_meta"] - 0.5) * 2
    oof["ret_next"] = close.pct_change().shift(-1).reindex(test_idx)

    return WalkForwardResult(
        signals=oof,
        perf_market=perf.compute_performance(oof["signal_market"] * oof["ret_next"], benchmark_returns=oof["ret_next"]),
        perf_swarm=perf.compute_performance(oof["signal_swarm"] * oof["ret_next"], benchmark_returns=oof["ret_next"]),
        perf_hybrid=perf.compute_performance(oof["signal_hybrid"] * oof["ret_next"], benchmark_returns=oof["ret_next"]),
        ic=perf.compute_ic(oof["p_meta"], fwd_ret.reindex(oof.index)),
        data_quality=_finalize_data_quality(swarm_quality or {}, oof),
    )


def _finalize_data_quality(swarm_quality: dict, signals) -> dict:
    p_swarm = signals.get("p_swarm") if signals is not None and len(signals) else None
    signal_swarm = signals.get("signal_swarm") if signals is not None and len(signals) else None
    p_unique = int(p_swarm.nunique(dropna=True)) if p_swarm is not None else 0
    signal_unique = int(signal_swarm.nunique(dropna=True)) if signal_swarm is not None else 0
    signal_abs_sum = float(signal_swarm.fillna(0.0).abs().sum()) if signal_swarm is not None else 0.0
    constant_warning = p_unique <= 1 or signal_unique <= 1 or signal_abs_sum == 0.0
    swarm = {
        **(swarm_quality or {}),
        "p_swarm_unique": p_unique,
        "signal_swarm_unique": signal_unique,
        "constant_signal_warning": bool(constant_warning),
    }
    return {"swarm": swarm}
