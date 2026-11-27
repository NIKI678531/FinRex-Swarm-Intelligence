"""Historical backtest adapter for the financial price-forecast model.

This keeps the Quant Backtest Lab contract intact while swapping the signal
engine from the two-tower model to the same interpretable ingredients used by
the live financial forecast services: technical votes, news/OASIS sentiment
factors, volume confirmation, and a composite directional probability.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Optional

from ..features.swarm_factors import compute_swarm_factors
from . import performance as perf


@dataclass
class FinancialForecastBacktestResult:
    signals: object
    perf_market: dict
    perf_swarm: dict
    perf_hybrid: dict
    ic: dict
    data_quality: dict


def run_financial_forecast_backtest(
    ohlcv,
    symbol: str,
    horizon: int = 5,
    swarm_source_mode: str = "auto",
    oasis_simulation_id: Optional[str] = None,
    sentiment_sources: Optional[list[str]] = None,
) -> FinancialForecastBacktestResult:
    """Run a no-lookahead historical version of FinancialForecastService.

    ``market`` in the UI is the technical-only leg, ``swarm`` is the
    sentiment/OASIS leg, and ``hybrid`` is the current price-forecast composite.
    """
    import pandas as pd

    horizon = max(1, int(horizon or 1))
    close = ohlcv["close"].astype(float)
    fwd_ret = close.shift(-horizon) / close - 1.0

    swarm = compute_swarm_factors(
        symbol,
        ohlcv.index.min(),
        ohlcv.index.max(),
        source_mode=swarm_source_mode,
        oasis_simulation_id=oasis_simulation_id,
        sentiment_sources=sentiment_sources,
    )
    swarm_quality = dict(swarm.attrs.get("data_quality") or {})
    swarm = swarm.reindex(ohlcv.index).ffill(limit=3)
    swarm_quality["effective_rows"] = int((~swarm.isna().all(axis=1)).sum()) if len(swarm) else 0
    swarm_quality["coverage_ratio"] = swarm_quality["effective_rows"] / len(swarm) if len(swarm) else 0.0

    rows = []
    warmup = min(max(70, horizon * 12), max(20, len(ohlcv) // 3))
    for pos in range(warmup, max(warmup, len(ohlcv) - horizon)):
        hist = ohlcv.iloc[:pos + 1]
        score = _score_at_bar(hist, swarm.iloc[pos] if pos < len(swarm) else None, horizon)
        ts = ohlcv.index[pos]
        rows.append({
            "p_market": score["p_market"],
            "p_swarm": score["p_swarm"],
            "p_meta": score["p_hybrid"],
            "signal_market": _signal(score["p_market"]),
            "signal_swarm": _signal(score["p_swarm"]),
            "signal_hybrid": _signal(score["p_hybrid"]),
            "vol_5d": score["vol_5d"],
            "vol_20d": score["vol_20d"],
            "volume_z": score["volume_z"],
            "event_flag": score["event_flag"],
            "technical_factor": score["technical_factor"],
            "sentiment_factor": score["sentiment_factor"],
            "oasis_pulse_factor": score["oasis_pulse_factor"],
            "volume_factor": score["volume_factor"],
            "model_score": score["composite"],
            "price_model_direction": score["direction"],
        } | score["weights"])

    if rows:
        signals = pd.DataFrame(rows, index=ohlcv.index[warmup:warmup + len(rows)])
    else:
        signals = pd.DataFrame(columns=[
            "p_market", "p_swarm", "p_meta",
            "signal_market", "signal_swarm", "signal_hybrid", "ret_next",
        ], index=ohlcv.index[:0])
    signals["ret_next"] = close.pct_change().shift(-1).reindex(signals.index)

    perf_m = perf.compute_performance(signals["signal_market"] * signals["ret_next"], benchmark_returns=signals["ret_next"])
    perf_s = perf.compute_performance(signals["signal_swarm"] * signals["ret_next"], benchmark_returns=signals["ret_next"])
    perf_h = perf.compute_performance(signals["signal_hybrid"] * signals["ret_next"], benchmark_returns=signals["ret_next"])
    ic = perf.compute_ic(signals["p_meta"], fwd_ret.reindex(signals.index))

    return FinancialForecastBacktestResult(
        signals=signals,
        perf_market=perf_m,
        perf_swarm=perf_s,
        perf_hybrid=perf_h,
        ic=ic,
        data_quality={
            "swarm": _finalize_quality(swarm_quality, signals),
            "price_forecast_model": {
                "engine": "financial_forecast_backtest_v1",
                "horizon_days": horizon,
                "warmup_bars": warmup,
                "foundation_forecast": "disabled_for_walk_forward_no_lookahead",
            },
        },
    )


def _score_at_bar(hist, swarm_row: Any, horizon: int) -> dict:
    rows = [_ohlcv_row(idx, row) for idx, row in hist.iterrows()]
    signal = _technical_signal(rows, horizon)
    technical = _clamp(float(signal.get("score") or 0.0) / 6.0) if signal.get("ok") else 0.0
    volume = _volume_factor(rows)

    swarm_available = _swarm_row_available(swarm_row)
    sentiment = _swarm_sentiment_factor(swarm_row) if swarm_available else float("nan")
    pulse = _swarm_pulse_factor(swarm_row) if swarm_available else float("nan")
    sentiment = sentiment if _is_finite(sentiment) else 0.0
    pulse = pulse if _is_finite(pulse) else 0.0

    target_weights = {
        "technical": 0.55 if signal.get("ok") else 0.0,
        "sentiment": 0.30 if swarm_available else 0.0,
        "volume": 0.07 if len(rows) >= 22 else 0.0,
        "oasis_pulse": 0.08 if swarm_available else 0.0,
    }
    total = sum(target_weights.values()) or 1.0
    weights = {f"w_{key}": value / total for key, value in target_weights.items()}
    composite = (
        technical * weights["w_technical"]
        + sentiment * weights["w_sentiment"]
        + volume * weights["w_volume"]
        + pulse * weights["w_oasis_pulse"]
    )
    swarm_composite = _clamp(0.72 * sentiment + 0.28 * pulse)

    return {
        "p_market": _prob(technical),
        "p_swarm": _prob(swarm_composite),
        "p_hybrid": _prob(composite),
        "technical_factor": round(technical, 6),
        "sentiment_factor": round(sentiment, 6),
        "oasis_pulse_factor": round(pulse, 6),
        "volume_factor": round(volume, 6),
        "composite": round(composite, 6),
        "direction": "up" if composite > 0.08 else ("down" if composite < -0.08 else "neutral"),
        "vol_5d": _rolling_vol(hist["close"].astype(float), 5),
        "vol_20d": _rolling_vol(hist["close"].astype(float), 20),
        "volume_z": _volume_z(hist),
        "event_flag": abs(pulse),
        "weights": {key: round(value, 6) for key, value in weights.items()},
    }


def _technical_signal(rows: list[dict], horizon: int) -> dict:
    try:
        from ...services.asset_forecast.signal_engine import compute_signals

        return compute_signals(rows, horizon_days=horizon)
    except Exception:
        return {"ok": False, "score": 0.0}


def _ohlcv_row(ts, row) -> dict:
    return {
        "date": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
        "open": _float(row.get("open"), row.get("close")),
        "high": _float(row.get("high"), row.get("close")),
        "low": _float(row.get("low"), row.get("close")),
        "close": _float(row.get("close"), 0.0),
        "volume": _float(row.get("volume"), 0.0),
    }


def _swarm_sentiment_factor(row: Any) -> float:
    if row is None:
        return float("nan")
    sentiment = _float(_get(row, "sentiment_mean"), float("nan"))
    bull = _float(_get(row, "bull_ratio"), 0.0)
    kol = _float(_get(row, "kol_lead_signal"), 0.0)
    polarization = abs(_float(_get(row, "polarization"), 0.0))
    if not _is_finite(sentiment) and not _is_finite(bull) and not _is_finite(kol):
        return float("nan")
    return _clamp(math.tanh(0.65 * _zero_nan(sentiment) + 0.25 * _zero_nan(bull) + 0.2 * _zero_nan(kol) - 0.12 * polarization))


def _swarm_pulse_factor(row: Any) -> float:
    if row is None:
        return float("nan")
    event = _float(_get(row, "event_intensity"), float("nan"))
    velocity = _float(_get(row, "sentiment_velocity"), 0.0)
    consensus = _float(_get(row, "consensus_speed"), 0.0)
    if not _is_finite(event) and not _is_finite(velocity) and not _is_finite(consensus):
        return float("nan")
    return _clamp(math.tanh(0.55 * _zero_nan(event) + 0.25 * _zero_nan(velocity) + 0.20 * _zero_nan(consensus)))


def _swarm_row_available(row: Any) -> bool:
    if row is None:
        return False
    keys = (
        "sentiment_mean", "sentiment_velocity", "polarization",
        "consensus_speed", "bull_ratio", "kol_lead_signal", "event_intensity",
    )
    return any(_is_finite(_get(row, key)) for key in keys)


def _volume_factor(rows: list[dict]) -> float:
    if len(rows) < 22:
        return 0.0
    last = rows[-1]
    prev = rows[-2]
    avg_vol = sum(float(r.get("volume") or 0.0) for r in rows[-21:-1]) / 20.0
    if avg_vol <= 0 or float(last.get("volume") or 0.0) < avg_vol * 1.35:
        return 0.0
    prev_close = float(prev.get("close") or 0.0)
    if prev_close <= 0:
        return 0.0
    ret = float(last.get("close") or 0.0) / prev_close - 1.0
    if ret > 0.01:
        return 0.18
    if ret < -0.01:
        return -0.18
    return 0.0


def _rolling_vol(close, window: int) -> float:
    ret = close.pct_change().tail(window).dropna()
    return _float(ret.std(ddof=0), 0.0)


def _volume_z(hist) -> float:
    vol = hist["volume"].astype(float).tail(20)
    if len(vol) < 5:
        return 0.0
    sd = vol.std(ddof=0)
    if not sd:
        return 0.0
    return _clamp((float(vol.iloc[-1]) - float(vol.mean())) / float(sd), -5.0, 5.0)


def _finalize_quality(swarm_quality: dict, signals) -> dict:
    p_swarm = signals.get("p_swarm") if signals is not None and len(signals) else None
    signal_swarm = signals.get("signal_swarm") if signals is not None and len(signals) else None
    p_unique = int(p_swarm.nunique(dropna=True)) if p_swarm is not None else 0
    signal_unique = int(signal_swarm.nunique(dropna=True)) if signal_swarm is not None else 0
    signal_abs_sum = float(signal_swarm.fillna(0.0).abs().sum()) if signal_swarm is not None else 0.0
    return {
        **(swarm_quality or {}),
        "p_swarm_unique": p_unique,
        "signal_swarm_unique": signal_unique,
        "constant_signal_warning": bool(p_unique <= 1 or signal_unique <= 1 or signal_abs_sum == 0.0),
        "model_family": "financial_forecast",
    }


def _signal(prob: float) -> float:
    return _clamp((float(prob) - 0.5) * 2.0)


def _prob(score: float) -> float:
    return round(max(0.15, min(0.85, 0.5 + float(score) * 0.32)), 6)


def _clamp(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def _get(row: Any, key: str) -> Any:
    try:
        return row.get(key)
    except AttributeError:
        try:
            return row[key]
        except Exception:
            return None


def _float(value: Any, default: Any = None) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else default
    except (TypeError, ValueError):
        return default


def _is_finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _zero_nan(value: Any) -> float:
    return float(value) if _is_finite(value) else 0.0
