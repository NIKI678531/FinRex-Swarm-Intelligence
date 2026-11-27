"""Risk metrics for ETF allocation.

Computes annualised volatility, max drawdown and a Sharpe-like ratio
from a list of close prices. Pure Python, no numpy dependency.
"""

from __future__ import annotations

import math
from typing import Dict, List

TRADING_DAYS = 252


def annualised_vol(returns: List[float]) -> float:
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / max(len(returns) - 1, 1)
    return math.sqrt(var) * math.sqrt(TRADING_DAYS)


def max_drawdown(closes: List[float]) -> float:
    if not closes:
        return 0.0
    peak = closes[0]
    worst = 0.0
    for c in closes:
        if c > peak:
            peak = c
        if peak > 0:
            dd = (c - peak) / peak
            if dd < worst:
                worst = dd
    return worst  # negative number, e.g. -0.18


def sharpe(returns: List[float], rf_annual: float = 0.04) -> float:
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / max(len(returns) - 1, 1)
    std = math.sqrt(var)
    if std == 0:
        return 0.0
    rf_daily = rf_annual / TRADING_DAYS
    return ((mean - rf_daily) / std) * math.sqrt(TRADING_DAYS)


def compute_risk(closes: List[float], returns: List[float]) -> Dict[str, float]:
    vol = annualised_vol(returns)
    dd = max_drawdown(closes)
    sh = sharpe(returns)
    return {
        "ann_vol": round(vol, 4),
        "max_drawdown": round(dd, 4),
        "sharpe": round(sh, 3),
    }


# ---------------------------------------------------------------------------
# Risk tier penalty for allocation scoring
# ---------------------------------------------------------------------------

_TIER_PENALTY = {
    "low": 0.0,
    "mid": 0.15,
    "high": 0.30,
    "very_high": 0.55,
}


def tier_penalty(tier: str) -> float:
    return _TIER_PENALTY.get((tier or "mid").lower(), 0.2)


# Allocation cap by risk tier (percent of portfolio)
_TIER_CAP = {
    "low": 0.50,
    "mid": 0.35,
    "high": 0.20,
    "very_high": 0.08,
}


def tier_cap(tier: str) -> float:
    return _TIER_CAP.get((tier or "mid").lower(), 0.25)
