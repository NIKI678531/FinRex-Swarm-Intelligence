"""Signal engine — converts indicators into a 5-day directional forecast.

Strategy (rule-based, deterministic):

    Trend votes:
        * SMA20 > SMA60                     +1
        * Close > EMA20                     +1
        * MACD line > signal line           +1
    Momentum votes:
        * 10d momentum > 0                  +1
        * 20d momentum > 0                  +1
    Mean-reversion guard:
        * RSI > 70  (overbought)            -1
        * RSI < 30  (oversold)              +1
    Volatility guard:
        * Close > Bollinger upper           -1   (extended)
        * Close < Bollinger lower           +1   (compressed)

The vote sum is mapped to a direction & confidence:
    score >= +3   →  bullish
    score <= -3   →  bearish
    otherwise     →  neutral

A 5-day expected return range is built from realised daily volatility
(``sigma * sqrt(5)``), centred on the *signed* score.

This is intentionally **not a machine-learning forecast** — it mirrors
QuantDinger's IndicatorStrategy philosophy of transparent, auditable
indicator votes. Outputs feed both UI cards and allocation weighting.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

from . import indicators as ind
from .risk_metrics import compute_risk

MIN_BARS = 70  # need enough history for SMA60 + RSI + MACD warmup


def compute_signals(
    rows: List[Dict[str, Any]],
    horizon_days: int = 1,
    foundation: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Compute all indicators on a list of OHLCV rows and return summary state.

    ``horizon_days`` controls the prediction window (default 1 = next trading
    day). It only changes the expected-return band width via ``sigma * sqrt(h)``;
    vote logic is unchanged so the direction/confidence stay consistent across
    windows.

    ``foundation`` is the optional output of
    ``quant.models.foundation_ensemble.predict_ensemble``. When supplied, the
    expected-return band is derived from Kronos/Chronos quantiles instead of
    the deterministic sigma*sqrt(h) fallback.
    """
    closes = [float(r["close"]) for r in rows if r.get("close")]
    highs = [float(r.get("high") or r.get("close") or 0.0) for r in rows]
    lows = [float(r.get("low") or r.get("close") or 0.0) for r in rows]
    n = len(closes)
    if n < MIN_BARS:
        return {
            "ok": False,
            "reason": f"insufficient_history (need >= {MIN_BARS}, got {n})",
            "bars": n,
        }

    sma20 = ind.sma(closes, 20)
    sma60 = ind.sma(closes, 60)
    ema20 = ind.ema(closes, 20)
    rsi14 = ind.rsi(closes, 14)
    macd_pkg = ind.macd(closes, 12, 26, 9)
    boll = ind.bollinger(closes, 20, 2.0)
    atr14 = ind.atr(highs, lows, closes, 14)
    mom10 = ind.momentum(closes, 10)
    mom20 = ind.momentum(closes, 20)
    rets = ind.daily_returns(closes)

    last = n - 1
    last_close = closes[last]

    # ---- Vote ----
    votes: List[Tuple[str, int, str]] = []  # (label, weight, polarity)

    if sma20[last] is not None and sma60[last] is not None:
        if sma20[last] > sma60[last]:
            votes.append(("SMA20>SMA60", +1, "bull"))
        else:
            votes.append(("SMA20<=SMA60", -1, "bear"))

    if ema20[last] is not None:
        if last_close > ema20[last]:
            votes.append(("Close>EMA20", +1, "bull"))
        else:
            votes.append(("Close<=EMA20", -1, "bear"))

    if macd_pkg["macd"][last] is not None and macd_pkg["signal"][last] is not None:
        if macd_pkg["macd"][last] > macd_pkg["signal"][last]:
            votes.append(("MACD>Signal", +1, "bull"))
        else:
            votes.append(("MACD<=Signal", -1, "bear"))

    if mom10[last] is not None:
        if mom10[last] > 0:
            votes.append(("Mom10+", +1, "bull"))
        else:
            votes.append(("Mom10-", -1, "bear"))

    if mom20[last] is not None:
        if mom20[last] > 0:
            votes.append(("Mom20+", +1, "bull"))
        else:
            votes.append(("Mom20-", -1, "bear"))

    if rsi14[last] is not None:
        if rsi14[last] > 70:
            votes.append(("RSI>70 overbought", -1, "bear"))
        elif rsi14[last] < 30:
            votes.append(("RSI<30 oversold", +1, "bull"))

    if boll["upper"][last] is not None and boll["lower"][last] is not None:
        if last_close > boll["upper"][last]:
            votes.append(("Close>BollUpper", -1, "bear"))
        elif last_close < boll["lower"][last]:
            votes.append(("Close<BollLower", +1, "bull"))

    score = sum(w for _, w, _ in votes)
    bullish_votes = sum(1 for _, w, _ in votes if w > 0)
    bearish_votes = sum(1 for _, w, _ in votes if w < 0)
    total_votes = bullish_votes + bearish_votes

    # ---- Direction & confidence ----
    if score >= 3:
        direction = "bullish"
    elif score <= -3:
        direction = "bearish"
    else:
        direction = "neutral"

    confidence = min(1.0, abs(score) / 6.0) if total_votes else 0.0
    confidence = round(confidence, 3)

    # ---- Expected 5-day range from realised vol ----
    recent_rets = [r for r in rets[-30:] if r != 0.0]
    if len(recent_rets) >= 5:
        mean_r = sum(recent_rets) / len(recent_rets)
        var_r = sum((r - mean_r) ** 2 for r in recent_rets) / max(len(recent_rets) - 1, 1)
        sigma = math.sqrt(var_r)
    else:
        sigma = 0.01

    horizon = max(1, int(horizon_days))
    sigma_h = sigma * math.sqrt(horizon)

    # Prefer Kronos/Chronos foundation quantiles over the deterministic sigma
    # band whenever available — gives a real model-based point estimate of
    # next-day price rather than a vol-only envelope centred on the score.
    fe_price = None
    fe_p10 = None
    fe_p90 = None
    price_source = "sigma_band"
    if foundation and last_close:
        try:
            fe_price = foundation.get("predicted_price")
            fe_p10 = foundation.get("p10")
            fe_p90 = foundation.get("p90")
            if fe_price and fe_p10 and fe_p90:
                price_source = foundation.get("mode") or "foundation"
        except Exception:
            fe_price = fe_p10 = fe_p90 = None

    if price_source != "sigma_band" and last_close:
        central_pct = round((fe_price / last_close - 1.0) * 100, 2)
        lower_pct = round((fe_p10 / last_close - 1.0) * 100, 2)
        upper_pct = round((fe_p90 / last_close - 1.0) * 100, 2)
    else:
        # Fallback: sigma * sqrt(h) band centred on a signed bias from score
        bias = (score / 6.0) * sigma_h * 0.6
        lower_pct = round((bias - sigma_h) * 100, 2)
        upper_pct = round((bias + sigma_h) * 100, 2)
        central_pct = round(bias * 100, 2)

    risk = compute_risk(closes, rets[-120:] if len(rets) >= 120 else rets)

    return {
        "ok": True,
        "bars": n,
        "last_close": round(last_close, 4),
        "as_of": rows[-1].get("date"),
        "indicators_last": {
            "sma20": _round(sma20[last]),
            "sma60": _round(sma60[last]),
            "ema20": _round(ema20[last]),
            "rsi14": _round(rsi14[last]),
            "macd": _round(macd_pkg["macd"][last]),
            "macd_signal": _round(macd_pkg["signal"][last]),
            "macd_hist": _round(macd_pkg["hist"][last]),
            "boll_upper": _round(boll["upper"][last]),
            "boll_lower": _round(boll["lower"][last]),
            "atr14": _round(atr14[last]),
            "mom10_pct": _pct(mom10[last]),
            "mom20_pct": _pct(mom20[last]),
        },
        "votes": [
            {"label": lbl, "weight": w, "polarity": p}
            for lbl, w, p in votes
        ],
        "score": score,
        "direction": direction,
        "confidence": confidence,
        "horizon_days": horizon,
        "expected_return_pct": {
            "central": central_pct,
            "lower": lower_pct,
            "upper": upper_pct,
        },
        "price_source": price_source,
        "predicted_price": round(fe_price, 4) if fe_price else None,
        "predicted_band": (
            {"low": round(fe_p10, 4), "high": round(fe_p90, 4)}
            if (fe_p10 and fe_p90) else None
        ),
        "foundation": foundation if foundation else None,
        "risk": risk,
    }


def _round(v):
    if v is None:
        return None
    try:
        return round(float(v), 4)
    except Exception:
        return None


def backtest_hit_rate(rows: List[Dict[str, Any]], horizon_days: int = 1) -> Dict[str, Any]:
    """Walk-forward backtest of the same indicator-vote rules.

    For every historical bar where all required indicators have warmed up,
    compute the vote score using only data up to that bar, then look ahead
    ``horizon_days`` trading days and record whether the direction was right.

    Neutral predictions (|score| < 3) are tracked separately and excluded
    from the hit-rate denominator (we only judge directional calls).
    """
    closes = [float(r["close"]) for r in rows if r.get("close")]
    highs = [float(r.get("high") or r.get("close") or 0.0) for r in rows]
    lows = [float(r.get("low") or r.get("close") or 0.0) for r in rows]
    n = len(closes)
    h = max(1, int(horizon_days))
    if n < MIN_BARS + h:
        return {"ok": False, "reason": "insufficient_history", "samples": 0}

    sma20 = ind.sma(closes, 20)
    sma60 = ind.sma(closes, 60)
    ema20 = ind.ema(closes, 20)
    rsi14 = ind.rsi(closes, 14)
    macd_pkg = ind.macd(closes, 12, 26, 9)
    boll = ind.bollinger(closes, 20, 2.0)
    mom10 = ind.momentum(closes, 10)
    mom20 = ind.momentum(closes, 20)

    samples = 0
    bullish_n = bullish_hit = 0
    bearish_n = bearish_hit = 0
    neutral_n = 0
    directional_n = directional_hit = 0

    for i in range(MIN_BARS - 1, n - h):
        score = 0
        ok_inputs = (
            sma20[i] is not None and sma60[i] is not None
            and ema20[i] is not None
            and macd_pkg["macd"][i] is not None and macd_pkg["signal"][i] is not None
            and mom10[i] is not None and mom20[i] is not None
        )
        if not ok_inputs:
            continue
        score += 1 if sma20[i] > sma60[i] else -1
        score += 1 if closes[i] > ema20[i] else -1
        score += 1 if macd_pkg["macd"][i] > macd_pkg["signal"][i] else -1
        score += 1 if mom10[i] > 0 else -1
        score += 1 if mom20[i] > 0 else -1
        if rsi14[i] is not None:
            if rsi14[i] > 70:
                score -= 1
            elif rsi14[i] < 30:
                score += 1
        if boll["upper"][i] is not None and boll["lower"][i] is not None:
            if closes[i] > boll["upper"][i]:
                score -= 1
            elif closes[i] < boll["lower"][i]:
                score += 1

        future_ret = (closes[i + h] / closes[i]) - 1.0
        samples += 1
        if score >= 3:
            bullish_n += 1
            directional_n += 1
            if future_ret > 0:
                bullish_hit += 1
                directional_hit += 1
        elif score <= -3:
            bearish_n += 1
            directional_n += 1
            if future_ret < 0:
                bearish_hit += 1
                directional_hit += 1
        else:
            neutral_n += 1

    def _rate(hit, n_):
        return round(hit / n_, 3) if n_ > 0 else None

    return {
        "ok": True,
        "horizon_days": h,
        "samples": samples,
        "directional_samples": directional_n,
        "neutral_samples": neutral_n,
        "hit_rate": _rate(directional_hit, directional_n),
        "bullish_hit_rate": _rate(bullish_hit, bullish_n),
        "bearish_hit_rate": _rate(bearish_hit, bearish_n),
        "bullish_count": bullish_n,
        "bearish_count": bearish_n,
    }


def _pct(v):
    if v is None:
        return None
    try:
        return round(float(v) * 100, 2)
    except Exception:
        return None
