"""Map a FinRex forecast to a Polymarket binary outcome probability.

For the daily BTC up/down market the mapping is 1:1 — the forecast already
predicts directional probability over the same 24h window. For richer
"strike" markets ("BTC > $X by date") we use a lognormal CDF translation
of the FinRex target_price_range.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple


def map_finrex_to_polymarket_probability(forecast: Dict[str, Any]) -> Dict[str, Any]:
    """Translate a 1d directional forecast into Polymarket YES/NO probabilities.

    Returns a dict::

        {
            "side": "YES" | "NO" | "SKIP",
            "p_yes": 0.62,
            "p_no": 0.38,
            "direction": "up",
            "confidence_score": 0.74,
            "skip_reason": None,
        }
    """
    direction = (forecast.get("direction") or "").lower()
    probability = _safe_float(forecast.get("probability"), 0.5)
    confidence = _safe_float(forecast.get("confidence_score"), 0.0)
    horizon_days = _safe_float(forecast.get("horizon_days"), 1)

    if horizon_days != 1:
        return _skip("forecast horizon is not 1d; cannot align to daily market")

    if direction in ("neutral", "flat", ""):
        return _skip("forecast direction is neutral; no binary edge")

    if direction in ("up", "bull", "bullish"):
        p_yes = max(0.0, min(1.0, probability))
        side = "YES"
    elif direction in ("down", "bear", "bearish"):
        # `probability` from forecast is the probability of the *predicted*
        # direction, i.e. P(down). YES side of the market = P(up).
        p_yes = max(0.0, min(1.0, 1.0 - probability))
        side = "NO"
    else:
        return _skip(f"unknown direction: {direction}")

    return {
        "side": side,
        "p_yes": round(p_yes, 4),
        "p_no": round(1 - p_yes, 4),
        "direction": direction,
        "confidence_score": confidence,
        "skip_reason": None,
    }


def edge_vs_market(p_model: float, market_yes_price: float, side: str) -> float:
    """Edge (positive = bet has positive EV before fees/slippage).

    For YES side: edge = p_model - market_yes_price.
    For NO side: edge = (1 - p_model) - (1 - market_yes_price) = market_yes_price - p_model
    Always returned as: model_prob - implied_prob_for_chosen_side.
    """
    if side.upper() == "YES":
        return p_model - market_yes_price
    if side.upper() == "NO":
        return (1 - p_model) - (1 - market_yes_price)
    return 0.0


def kelly_fraction(p: float, payout_multiple: float, kelly_fraction_cap: float = 0.5) -> float:
    """Half-Kelly (default) fraction of bankroll for a binary bet.

    Standard Kelly for a bet that pays b net on win, loses 1 on loss:
        f* = (b*p - q) / b   where q = 1 - p
    payout_multiple here is gross (e.g. 1/0.55 = 1.818 → b = 0.818).
    Returns clamped to [0, 1].
    """
    if payout_multiple <= 1.0 or p <= 0:
        return 0.0
    b = payout_multiple - 1.0
    q = 1.0 - p
    f_star = (b * p - q) / b
    if f_star <= 0:
        return 0.0
    return max(0.0, min(1.0, f_star * kelly_fraction_cap))


def map_to_strike_market(
    forecast: Dict[str, Any],
    strike_price: float,
    current_price: float,
) -> Dict[str, Any]:
    """Lognormal CDF mapping for a "BTC > strike" market.

    Uses the forecast's expected return + 1d realized vol to derive
    P(BTC_close > strike). Falls back to neutral 0.5 if inputs missing.
    """
    target = forecast.get("target_price_range") or {}
    expected_close = _safe_float(target.get("midpoint"), current_price)
    sigma_pct = _safe_float(target.get("realized_vol_pct"), None)
    if sigma_pct is None or sigma_pct <= 0 or current_price <= 0:
        return {
            "p_yes": 0.5, "p_no": 0.5, "side": "SKIP",
            "skip_reason": "missing realized vol for lognormal mapping",
        }
    # log-mean drift implied by expected close
    mu = math.log(max(expected_close, 1e-9) / current_price)
    sigma = sigma_pct / 100.0
    z = (math.log(strike_price / current_price) - mu) / sigma
    # P(BTC_T > strike) = 1 - Phi(z)
    p_above = 1.0 - _norm_cdf(z)
    p_above = max(0.0, min(1.0, p_above))
    side = "YES" if p_above >= 0.5 else "NO"
    return {
        "p_yes": round(p_above, 4),
        "p_no": round(1 - p_above, 4),
        "side": side,
        "expected_close": expected_close,
        "sigma": sigma,
        "skip_reason": None,
    }


# ----------------------------------------------------------------------
def _skip(reason: str) -> Dict[str, Any]:
    return {
        "side": "SKIP",
        "p_yes": 0.5,
        "p_no": 0.5,
        "direction": "neutral",
        "confidence_score": 0.0,
        "skip_reason": reason,
    }


def _safe_float(v: Any, default: Optional[float]) -> Optional[float]:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
