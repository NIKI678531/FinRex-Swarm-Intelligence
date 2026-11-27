"""Forward (single-step) inference adapter for the three validation models.

Bridges the weekly validation desk to the three backtest model families
(`price_point_calibrated_ml`, `two_tower`, `financial_forecast`) by exposing a
single, normalized entry point that returns either a *price distribution* or a
*directional probability* for the upcoming `horizon` window.

Every branch degrades gracefully: if a heavy model is unavailable (missing
foundation weights, sklearn, or insufficient history) it falls back to a
deterministic, dependency-light estimate so the desk never hard-fails.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

from .model_registry import output_kind, resolve_model

logger = logging.getLogger("finrex.validation.forward")


def _to_dataframe(market_rows: List[Dict[str, Any]]):
    """Convert loader rows ({ts, open, high, low, close, volume}) into a
    DatetimeIndex OHLCV DataFrame, or return None if pandas is unavailable."""
    try:
        import pandas as pd
    except Exception:  # noqa: BLE001
        return None
    if not market_rows:
        return None
    idx = []
    data = {"open": [], "high": [], "low": [], "close": [], "volume": []}
    for r in market_rows:
        ts = r.get("ts") or r.get("date")
        try:
            idx.append(pd.to_datetime(ts, utc=True))
        except Exception:  # noqa: BLE001
            idx.append(pd.Timestamp.utcnow())
        for k in data:
            data[k].append(float(r.get(k) or 0.0))
    df = pd.DataFrame(data, index=pd.DatetimeIndex(idx))
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def _direction_result(p_up: float, *, mode: str, warning: Optional[str] = None) -> Dict[str, Any]:
    p_up = max(0.01, min(0.99, float(p_up)))
    return {
        "kind": "direction",
        "p_up": p_up,
        "mode": mode,
        "warning": warning,
    }


def _price_dist_result(forecast: Dict[str, Any], *, mode: str, warning: Optional[str] = None) -> Dict[str, Any]:
    return {
        "kind": "price_dist",
        "p_up": max(0.01, min(0.99, float(forecast.get("p_up", 0.5)))),
        "p10": float(forecast.get("p10")),
        "p50": float(forecast.get("p50")),
        "p90": float(forecast.get("p90")),
        "predicted_price": float(forecast.get("predicted_price", forecast.get("p50"))),
        "last_close": float(forecast.get("last_close", 0.0) or 0.0),
        "expected_return": float(forecast.get("expected_return", 0.0) or 0.0),
        "calibration_applied": bool(forecast.get("calibration_applied", False)),
        "mode": mode,
        "warning": warning or forecast.get("warning"),
    }


# ----------------------------------------------------------------------
# price_point_calibrated_ml  →  price distribution (Kronos + Chronos)
# ----------------------------------------------------------------------
def _forecast_price_point(symbol: str, df, horizon: int) -> Dict[str, Any]:
    from ...quant.models.price_point_calibrator import (
        apply_latest_calibration,
        foundation_or_fallback_forecast,
    )

    raw, reason = foundation_or_fallback_forecast(df, horizon=horizon)
    calibrated = apply_latest_calibration(symbol, horizon, df, raw) or raw
    mode = str(calibrated.get("mode") or raw.get("mode") or "price_point_calibrated_ml")
    return _price_dist_result(calibrated, mode=mode, warning=reason)


# ----------------------------------------------------------------------
# two_tower  →  directional probability (Market + Swarm towers)
# ----------------------------------------------------------------------
def _forecast_two_tower(symbol: str, df, horizon: int) -> Dict[str, Any]:
    try:
        from ...quant.features.market_features import compute_market_features
        from ...quant.models.tower_market import MarketTower
        from ...quant.models.tower_swarm import SwarmTower

        close = df["close"]
        if len(close.dropna()) < horizon + 10:
            return _direction_result(0.5, mode="two_tower_insufficient_history",
                                     warning="not enough history to fit towers")

        market_feats = compute_market_features(df)
        # Fit on rows whose forward label is observable (drop last `horizon`).
        train_idx = df.index[:-horizon] if len(df.index) > horizon else df.index
        mt = MarketTower().fit(market_feats.loc[train_idx], close.loc[train_idx], horizon=horizon)
        p_market = float(mt.predict_proba(market_feats.tail(1)).iloc[-1])

        p_swarm = None
        try:
            from ...quant.features.swarm_factors import compute_swarm_factors
            from ...quant import config as qcfg

            swarm = compute_swarm_factors(
                symbol, df.index.min(), df.index.max(), source_mode="auto",
            )
            swarm = swarm.reindex(df.index).ffill(limit=qcfg.SWARM_FFILL_LIMIT)
            if not swarm.dropna(how="all").empty:
                st = SwarmTower().fit(swarm.loc[train_idx], close.loc[train_idx], horizon=horizon)
                p_swarm = float(st.predict_proba(swarm.tail(1)).iloc[-1])
        except Exception as exc:  # noqa: BLE001
            logger.info("two_tower swarm branch unavailable: %s", exc)

        if p_swarm is None:
            p_up = p_market
            warning = "swarm tower unavailable; market tower only"
        else:
            p_up = 0.5 * (p_market + p_swarm)
            warning = None
        return _direction_result(p_up, mode="two_tower", warning=warning)
    except Exception as exc:  # noqa: BLE001
        logger.warning("two_tower forward inference failed: %s", exc)
        return _direction_result(0.5, mode="two_tower_error", warning=str(exc))


# ----------------------------------------------------------------------
# financial_forecast  →  directional probability (interpretable composite)
# ----------------------------------------------------------------------
def _forecast_financial(symbol: str, df, horizon: int) -> Dict[str, Any]:
    try:
        from ...quant.backtest.financial_forecast import _score_at_bar

        swarm_row = None
        try:
            from ...quant.features.swarm_factors import compute_swarm_factors

            swarm = compute_swarm_factors(
                symbol, df.index.min(), df.index.max(), source_mode="auto",
            )
            swarm = swarm.reindex(df.index).ffill()
            if not swarm.dropna(how="all").empty:
                swarm_row = swarm.iloc[-1]
        except Exception as exc:  # noqa: BLE001
            logger.info("financial_forecast swarm branch unavailable: %s", exc)

        scored = _score_at_bar(df, swarm_row, horizon)
        p_up = float(scored.get("p_hybrid", 0.5))
        warning = None if swarm_row is not None else "sentiment factors unavailable; technical/volume only"
        return _direction_result(p_up, mode="financial_forecast", warning=warning)
    except Exception as exc:  # noqa: BLE001
        logger.warning("financial_forecast forward inference failed: %s", exc)
        return _direction_result(0.5, mode="financial_forecast_error", warning=str(exc))


# ----------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------
def forward_forecast(
    symbol: str,
    model_family: str,
    market_rows: List[Dict[str, Any]],
    *,
    horizon: int = 7,
) -> Dict[str, Any]:
    """Return a normalized forward forecast for `model_family`.

    Result shape:
        {kind: "price_dist", p_up, p10, p50, p90, predicted_price, last_close, mode, warning}
      or
        {kind: "direction", p_up, mode, warning}

    Never raises: on any failure returns a neutral directional result.
    """
    spec = resolve_model(model_family)
    key = spec["key"]
    df = _to_dataframe(market_rows)
    if df is None or "close" not in df or df["close"].dropna().empty:
        return _direction_result(0.5, mode=f"{key}_no_data", warning="no market history available")

    if output_kind(key) == "price_dist":
        try:
            return _forecast_price_point(symbol, df, horizon)
        except Exception as exc:  # noqa: BLE001
            logger.warning("price_point forward inference failed: %s", exc)
            return _direction_result(0.5, mode="price_point_error", warning=str(exc))
    if key == "two_tower":
        return _forecast_two_tower(symbol, df, horizon)
    if key == "financial_forecast":
        return _forecast_financial(symbol, df, horizon)
    return _direction_result(0.5, mode=f"{key}_unsupported", warning="unsupported model family")


def lognormal_bin_probabilities(
    bins: List[Dict[str, Any]],
    *,
    p10: float,
    p50: float,
    p90: float,
) -> List[float]:
    """Analytic terminal-price probability per bin assuming ln(P) ~ Normal.

    Fits (m, s) from the p10/p50/p90 quantiles and integrates the lognormal CDF
    across each [low, high) bin. Tail bins use low=None → -inf, high=None → +inf.
    """
    z80 = 1.2815515655446004
    p10 = max(float(p10), 1e-9)
    p50 = max(float(p50), 1e-9)
    p90 = max(float(p90), 1e-9)
    lo, hi = min(p10, p90), max(p10, p90)
    m = math.log(p50)
    s = (math.log(hi) - math.log(lo)) / (2.0 * z80)
    s = max(s, 1e-4)

    def _cdf(price: Optional[float]) -> float:
        if price is None:
            return None  # caller handles tails
        if price <= 0:
            return 0.0
        z = (math.log(price) - m) / s
        return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))

    probs: List[float] = []
    for b in bins:
        c_low = 0.0 if b.get("low") is None else _cdf(b.get("low"))
        c_high = 1.0 if b.get("high") is None else _cdf(b.get("high"))
        probs.append(max(0.0, c_high - c_low))
    total = sum(probs) or 1.0
    return [p / total for p in probs]
