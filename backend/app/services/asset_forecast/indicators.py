"""Pure-Python technical indicators.

Mirrors the dataframe-style indicator pattern used by QuantDinger
``IndicatorStrategy`` (see https://github.com/brokermr810/QuantDinger), but
stripped down to operate on plain Python lists of floats so the asset
forecast module can run with no extra dependencies beyond yfinance.

All functions return lists aligned 1-to-1 with the input length; positions
where the indicator is undefined contain ``None``.
"""

from __future__ import annotations

import math
from typing import List, Optional

Number = Optional[float]


# ---------------------------------------------------------------------------
# Moving averages
# ---------------------------------------------------------------------------

def sma(values: List[float], period: int) -> List[Number]:
    if period <= 0:
        return [None] * len(values)
    out: List[Number] = [None] * len(values)
    if len(values) < period:
        return out
    window_sum = sum(values[:period])
    out[period - 1] = window_sum / period
    for i in range(period, len(values)):
        window_sum += values[i] - values[i - period]
        out[i] = window_sum / period
    return out


def ema(values: List[float], period: int) -> List[Number]:
    out: List[Number] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    k = 2.0 / (period + 1)
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


# ---------------------------------------------------------------------------
# RSI (Wilder smoothing)
# ---------------------------------------------------------------------------

def rsi(values: List[float], period: int = 14) -> List[Number]:
    n = len(values)
    out: List[Number] = [None] * n
    if n <= period:
        return out
    gains = [0.0] * n
    losses = [0.0] * n
    for i in range(1, n):
        diff = values[i] - values[i - 1]
        gains[i] = max(diff, 0.0)
        losses[i] = max(-diff, 0.0)
    avg_gain = sum(gains[1:period + 1]) / period
    avg_loss = sum(losses[1:period + 1]) / period
    out[period] = _rsi_from(avg_gain, avg_loss)
    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out[i] = _rsi_from(avg_gain, avg_loss)
    return out


def _rsi_from(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


# ---------------------------------------------------------------------------
# MACD
# ---------------------------------------------------------------------------

def macd(
    values: List[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> dict:
    """Return ``{"macd": [...], "signal": [...], "hist": [...]}`` aligned to ``values``."""
    fast_line = ema(values, fast)
    slow_line = ema(values, slow)
    macd_line: List[Number] = [
        (f - s) if (f is not None and s is not None) else None
        for f, s in zip(fast_line, slow_line)
    ]
    # Build EMA of the macd_line where it is defined
    valid_idx = [i for i, v in enumerate(macd_line) if v is not None]
    signal_line: List[Number] = [None] * len(values)
    if len(valid_idx) >= signal:
        compact = [macd_line[i] for i in valid_idx]  # type: ignore[list-item]
        compact_signal = ema([float(v) for v in compact], signal)
        for offset, src_i in enumerate(valid_idx):
            signal_line[src_i] = compact_signal[offset]
    hist: List[Number] = [
        (m - s) if (m is not None and s is not None) else None
        for m, s in zip(macd_line, signal_line)
    ]
    return {"macd": macd_line, "signal": signal_line, "hist": hist}


# ---------------------------------------------------------------------------
# Bollinger Bands
# ---------------------------------------------------------------------------

def bollinger(values: List[float], period: int = 20, num_std: float = 2.0) -> dict:
    n = len(values)
    mid = sma(values, period)
    upper: List[Number] = [None] * n
    lower: List[Number] = [None] * n
    if n < period:
        return {"middle": mid, "upper": upper, "lower": lower}
    for i in range(period - 1, n):
        window = values[i - period + 1:i + 1]
        mean = mid[i] or 0.0
        var = sum((x - mean) ** 2 for x in window) / period
        std = math.sqrt(var)
        upper[i] = mean + num_std * std
        lower[i] = mean - num_std * std
    return {"middle": mid, "upper": upper, "lower": lower}


# ---------------------------------------------------------------------------
# ATR (uses high/low/close)
# ---------------------------------------------------------------------------

def atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[Number]:
    n = len(closes)
    out: List[Number] = [None] * n
    if n < period + 1:
        return out
    trs: List[float] = [0.0] * n
    for i in range(1, n):
        h, l, pc = highs[i], lows[i], closes[i - 1]
        trs[i] = max(h - l, abs(h - pc), abs(l - pc))
    # Wilder smoothing
    seed = sum(trs[1:period + 1]) / period
    out[period] = seed
    prev = seed
    for i in range(period + 1, n):
        prev = (prev * (period - 1) + trs[i]) / period
        out[i] = prev
    return out


# ---------------------------------------------------------------------------
# Momentum & returns
# ---------------------------------------------------------------------------

def momentum(values: List[float], period: int = 10) -> List[Number]:
    n = len(values)
    out: List[Number] = [None] * n
    for i in range(period, n):
        prev = values[i - period]
        if prev:
            out[i] = (values[i] - prev) / prev
    return out


def daily_returns(values: List[float]) -> List[float]:
    out: List[float] = [0.0]
    for i in range(1, len(values)):
        prev = values[i - 1]
        out.append((values[i] - prev) / prev if prev else 0.0)
    return out
