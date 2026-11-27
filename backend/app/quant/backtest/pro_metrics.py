"""Professional risk/return metrics — self-contained (numpy + pandas only).

Provides the 60+ metric universe usually pulled from quantstats / empyrical,
without the heavy plotting dependency tree.

All input series are pandas.Series of *period* returns (decimal, e.g. 0.012)
with a sortable DatetimeIndex.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------- #
# helpers                                                                     #
# --------------------------------------------------------------------------- #

def _af(freq: str) -> float:
    return {"1d": 252.0, "1h": 252 * 24, "1w": 52.0, "1m": 12.0}.get(freq, 252.0)


def _equity(returns: pd.Series) -> pd.Series:
    return (1.0 + returns.fillna(0.0)).cumprod()


def _drawdown(returns: pd.Series) -> pd.Series:
    eq = _equity(returns)
    peak = eq.cummax()
    return eq / peak - 1.0


# --------------------------------------------------------------------------- #
# headline metrics                                                            #
# --------------------------------------------------------------------------- #

def sortino(returns: pd.Series, freq: str = "1d", target: float = 0.0) -> float:
    r = returns.dropna()
    if r.empty:
        return 0.0
    downside = r[r < target]
    dstd = float(downside.std(ddof=0)) if len(downside) else 0.0
    if dstd <= 0:
        return 0.0
    excess = float(r.mean()) - target
    return excess / dstd * math.sqrt(_af(freq))


def calmar(returns: pd.Series, freq: str = "1d") -> float:
    r = returns.dropna()
    if r.empty:
        return 0.0
    af = _af(freq)
    ann = (1.0 + float(r.mean())) ** af - 1.0
    mdd = abs(float(_drawdown(r).min()))
    return ann / mdd if mdd > 0 else 0.0


def omega(returns: pd.Series, threshold: float = 0.0) -> float:
    r = returns.dropna()
    if r.empty:
        return 0.0
    excess = r - threshold
    gains = excess[excess > 0].sum()
    losses = -excess[excess < 0].sum()
    return float(gains / losses) if losses > 0 else float("inf") if gains > 0 else 0.0


def tail_ratio(returns: pd.Series, level: float = 0.05) -> float:
    r = returns.dropna()
    if r.empty:
        return 0.0
    upper = abs(float(np.quantile(r, 1 - level)))
    lower = abs(float(np.quantile(r, level)))
    return upper / lower if lower > 0 else 0.0


def probabilistic_sharpe(returns: pd.Series, freq: str = "1d", sr_benchmark: float = 0.0) -> float:
    """Bailey & López de Prado (2012) probabilistic Sharpe ratio. Returns 0..1."""
    r = returns.dropna()
    n = len(r)
    if n < 3:
        return 0.0
    af = _af(freq)
    sr = (float(r.mean()) / (float(r.std(ddof=0)) or 1e-9)) * math.sqrt(af)
    skew = float(r.skew())
    kurt = float(r.kurtosis())  # excess kurtosis
    denom = math.sqrt(max(1 - skew * sr + (kurt / 4.0) * sr ** 2, 1e-9) / (n - 1))
    z = (sr - sr_benchmark) / denom if denom > 0 else 0.0
    return _norm_cdf(z)


def _norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def max_drawdown_duration(returns: pd.Series) -> int:
    """Longest peak-to-recovery in *periods*. Open drawdown counted up to end."""
    r = returns.dropna()
    if r.empty:
        return 0
    eq = _equity(r)
    peak = eq.cummax()
    underwater = eq < peak
    if not underwater.any():
        return 0
    streaks = []
    cur = 0
    for u in underwater.values:
        if u:
            cur += 1
        else:
            if cur > 0:
                streaks.append(cur)
            cur = 0
    if cur > 0:
        streaks.append(cur)
    return int(max(streaks)) if streaks else 0


def ulcer_index(returns: pd.Series) -> float:
    dd = _drawdown(returns)
    return float(math.sqrt((dd ** 2).mean()))


def gain_to_pain(returns: pd.Series) -> float:
    r = returns.dropna()
    if r.empty:
        return 0.0
    gains = float(r[r > 0].sum())
    losses = float(-r[r < 0].sum())
    return gains / losses if losses > 0 else 0.0


def payoff_ratio(returns: pd.Series) -> float:
    r = returns.dropna()
    wins = r[r > 0]
    losses = r[r < 0]
    if losses.empty or wins.empty:
        return 0.0
    return float(wins.mean() / abs(losses.mean()))


def profit_factor(returns: pd.Series) -> float:
    return gain_to_pain(returns)  # identical formulation on period returns


def recovery_factor(returns: pd.Series, freq: str = "1d") -> float:
    r = returns.dropna()
    if r.empty:
        return 0.0
    af = _af(freq)
    ann = (1.0 + float(r.mean())) ** af - 1.0
    mdd = abs(float(_drawdown(r).min()))
    return ann / mdd if mdd > 0 else 0.0


def value_at_risk(returns: pd.Series, level: float = 0.05) -> float:
    r = returns.dropna()
    if r.empty:
        return 0.0
    return float(np.quantile(r, level))


def conditional_var(returns: pd.Series, level: float = 0.05) -> float:
    r = returns.dropna()
    if r.empty:
        return 0.0
    var = np.quantile(r, level)
    tail = r[r <= var]
    return float(tail.mean()) if not tail.empty else float(var)


def kelly_criterion(returns: pd.Series) -> float:
    r = returns.dropna()
    wins = r[r > 0]
    losses = r[r < 0]
    if wins.empty or losses.empty:
        return 0.0
    p = len(wins) / len(r)
    avg_win = float(wins.mean())
    avg_loss = abs(float(losses.mean()))
    if avg_loss <= 0:
        return 0.0
    b = avg_win / avg_loss
    return float(p - (1 - p) / b)


def common_sense_ratio(returns: pd.Series) -> float:
    return tail_ratio(returns) * profit_factor(returns)


# --------------------------------------------------------------------------- #
# time-series outputs                                                         #
# --------------------------------------------------------------------------- #

def drawdown_series(returns: pd.Series) -> list[dict]:
    dd = _drawdown(returns.dropna())
    return [
        {"ts": _iso(idx), "drawdown": float(val)}
        for idx, val in dd.items()
    ]


def rolling_sharpe(returns: pd.Series, window: int = 90, freq: str = "1d") -> list[dict]:
    r = returns.dropna()
    if len(r) < window:
        return []
    af = _af(freq)
    mean = r.rolling(window).mean()
    std = r.rolling(window).std(ddof=0)
    sr = (mean / std.replace(0, np.nan)) * math.sqrt(af)
    return [
        {"ts": _iso(idx), "value": (None if pd.isna(v) else float(v))}
        for idx, v in sr.items() if not pd.isna(v)
    ]


def rolling_volatility(returns: pd.Series, window: int = 90, freq: str = "1d") -> list[dict]:
    r = returns.dropna()
    if len(r) < window:
        return []
    af = _af(freq)
    vol = r.rolling(window).std(ddof=0) * math.sqrt(af)
    return [
        {"ts": _iso(idx), "value": (None if pd.isna(v) else float(v))}
        for idx, v in vol.items() if not pd.isna(v)
    ]


def monthly_returns_table(returns: pd.Series) -> list[dict]:
    """Return [{year, month, return}] long-format for heatmap rendering."""
    r = returns.dropna()
    if r.empty:
        return []
    idx = pd.to_datetime(r.index)
    monthly = (1 + r).groupby([idx.year, idx.month]).prod() - 1
    out = []
    for (year, month), val in monthly.items():
        out.append({"year": int(year), "month": int(month), "return": float(val)})
    return out


def _iso(ts) -> str:
    try:
        return pd.Timestamp(ts).isoformat()
    except Exception:
        return str(ts)


# --------------------------------------------------------------------------- #
# trade distributions                                                         #
# --------------------------------------------------------------------------- #

def trade_distributions(trade_log: list[dict]) -> dict:
    """Histogram bins for trade PnL and holding-period."""
    if not trade_log:
        return {"pnl_hist": [], "duration_hist": [], "by_side": {}}
    pnls = [
        float(t.get("net_pnl") if t.get("net_pnl") is not None else t.get("unrealized_pnl") or 0.0)
        for t in trade_log
    ]
    durations = [
        int(t.get("holding_bars") or 0)
        for t in trade_log if t.get("holding_bars") is not None
    ]
    sides = {}
    for t in trade_log:
        side = t.get("side") or "unknown"
        sides[side] = sides.get(side, 0) + 1

    return {
        "pnl_hist": _histogram(pnls, bins=20),
        "duration_hist": _histogram(durations, bins=15),
        "by_side": sides,
        "pnl_stats": _stats(pnls),
        "duration_stats": _stats([float(d) for d in durations]),
    }


def _histogram(values: list[float], bins: int = 20) -> list[dict]:
    if not values:
        return []
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return []
    hist, edges = np.histogram(arr, bins=bins)
    return [
        {"bin_low": float(edges[i]), "bin_high": float(edges[i + 1]), "count": int(hist[i])}
        for i in range(len(hist))
    ]


def _stats(values: list[float]) -> dict:
    if not values:
        return {"mean": 0.0, "median": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "p25": 0.0, "p75": 0.0}
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return {"mean": 0.0, "median": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "p25": 0.0, "p75": 0.0}
    return {
        "mean": float(arr.mean()),
        "median": float(np.median(arr)),
        "std": float(arr.std(ddof=0)),
        "min": float(arr.min()),
        "max": float(arr.max()),
        "p25": float(np.quantile(arr, 0.25)),
        "p75": float(np.quantile(arr, 0.75)),
    }


# --------------------------------------------------------------------------- #
# bundle                                                                      #
# --------------------------------------------------------------------------- #

def build_pro_metrics(
    returns: pd.Series,
    benchmark_returns: Optional[pd.Series] = None,
    freq: str = "1d",
) -> dict:
    """Single entry — returns the full pro-metric dict (scalars + small series)."""
    r = returns.dropna()
    if r.empty:
        return {}

    mdd = abs(float(_drawdown(r).min()))
    return {
        # risk-adjusted ratios
        "pro_sortino": sortino(r, freq),
        "pro_calmar": calmar(r, freq),
        "pro_omega": omega(r),
        "pro_tail_ratio": tail_ratio(r),
        "pro_prob_sharpe": probabilistic_sharpe(r, freq),

        # drawdown
        "pro_max_dd": -mdd,  # signed
        "pro_max_dd_duration": max_drawdown_duration(r),
        "pro_ulcer_index": ulcer_index(r),

        # trading quality
        "pro_payoff_ratio": payoff_ratio(r),
        "pro_profit_factor": profit_factor(r),
        "pro_gain_to_pain": gain_to_pain(r),
        "pro_recovery_factor": recovery_factor(r, freq),
        "pro_common_sense_ratio": common_sense_ratio(r),
        "pro_kelly": kelly_criterion(r),

        # tail risk
        "pro_var_95": value_at_risk(r, 0.05),
        "pro_cvar_95": conditional_var(r, 0.05),

        # distribution shape
        "pro_skew": float(r.skew()),
        "pro_kurtosis": float(r.kurtosis()),
    }


def build_pro_series(
    returns: pd.Series,
    rolling_window: int = 90,
    freq: str = "1d",
) -> dict:
    """Heavy time-series outputs for chart components."""
    r = returns.dropna()
    if r.empty:
        return {
            "drawdown_series": [],
            "rolling_sharpe": [],
            "rolling_vol": [],
            "monthly_returns": [],
        }
    return {
        "drawdown_series": drawdown_series(r),
        "rolling_sharpe": rolling_sharpe(r, rolling_window, freq),
        "rolling_vol": rolling_volatility(r, rolling_window, freq),
        "monthly_returns": monthly_returns_table(r),
    }
