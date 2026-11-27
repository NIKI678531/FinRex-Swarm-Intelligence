"""Weekly price-distribution forecast via Monte Carlo sampling.

Approach (v1):
- Estimate per-bar log-return mu, sigma from recent OHLCV history (default 90d).
- Bias mu by a "model edge" derived from current factor weights × normalized
  signals (sentiment, momentum, etc.) — keeps the forecast tied to the active
  `model_config`.
- Simulate `n_paths` random walks for `horizon_days`.
- Bucket the terminal price into the provided weekly bins → probability vector.

This is dependency-free (stdlib `random` only). It is a reasonable v1 that
will be replaced by a learned distributional head later.
"""

from __future__ import annotations

import logging
import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..historical_signals import data_loader_market
from ..historical_signals.multimodal_model import FEATURE_GROUPS, predict_weighted, sigmoid
from ..historical_signals.oasis_factor_builder import (
    OASIS_FACTOR_KEYS,
    build_oasis_daily_factors,
    neutral_oasis_factors,
)
from ..historical_signals.sentiment_replayer import merge_daily
from ..historical_signals import data_loader_binance, data_loader_fmp
from ..model_config import get_active_factor_weights, get_active_strategy_cfg
from .weekly_bins import assign_bin
from .forward_inference import forward_forecast, lognormal_bin_probabilities
from .model_registry import resolve_model

logger = logging.getLogger("finrex.validation.forecast")


def _log_returns(closes: List[float]) -> List[float]:
    rets: List[float] = []
    for i in range(1, len(closes)):
        if closes[i - 1] <= 0 or closes[i] <= 0:
            continue
        rets.append(math.log(closes[i] / closes[i - 1]))
    return rets


def _mean_std(values: List[float]) -> Tuple[float, float]:
    if not values:
        return 0.0, 0.0
    mean = sum(values) / len(values)
    if len(values) < 2:
        return mean, 0.0
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return mean, math.sqrt(max(var, 0.0))


def _zscored_signal(value: float, history: List[float]) -> float:
    if not history:
        return 0.0
    m, s = _mean_std(history)
    if s == 0:
        return 0.0
    return max(-3.0, min(3.0, (value - m) / s))


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _latest_oasis_features(
    cfg: Dict[str, Any],
    start_ts: datetime,
    end_ts: datetime,
) -> Tuple[Dict[str, float], Dict[str, Any]]:
    simulation_id = cfg.get("oasis_simulation_id")
    payload = build_oasis_daily_factors(simulation_id, start_ts, end_ts)
    rows_by_date = payload.get("rows_by_date") or {}
    if not rows_by_date:
        return neutral_oasis_factors(), payload.get("coverage") or {}
    latest_day = max(rows_by_date.keys())
    latest = {**neutral_oasis_factors(), **(rows_by_date.get(latest_day) or {})}
    return {key: float(latest.get(key, 0.0)) for key in OASIS_FACTOR_KEYS}, {
        **(payload.get("coverage") or {}),
        "latest_day": latest_day,
    }


def _build_model_bias(symbol: str, end_ts: datetime) -> Tuple[float, float, Dict[str, Any]]:
    """Return (extra log-return per day, sigma multiplier, debug payload).

    Pulls the last 30 days of sentiment + 90 days of price to compute a
    weighted score in roughly [-1, +1], then converts to a daily drift
    bump capped at ±0.5%/day. OASIS risk/disagreement/panic then widen the
    Monte Carlo sigma so crowded risk regimes produce fatter tails.
    """
    try:
        weights = get_active_factor_weights(symbol)
        cfg = get_active_strategy_cfg(symbol)
        ablation_mode = str(cfg.get("ablation_mode") or "market_text_oasis")
        feature_keys = FEATURE_GROUPS.get(ablation_mode) or FEATURE_GROUPS["market_text_oasis"]
        # Pull a short window of sentiment for "now" + a longer window for normalization.
        recent_start = end_ts - timedelta(days=14)
        norm_start = end_ts - timedelta(days=90)
        market_rows = data_loader_market.fetch_ohlcv(symbol, "1d", norm_start, end_ts)
        if not market_rows:
            return 0.0, 1.0, {"reason": "no market data"}

        # Fetch sentiment best-effort; if loaders fail we proceed with momentum-only.
        try:
            fmp = data_loader_fmp.fetch_window(symbol, recent_start, end_ts)
        except Exception:
            fmp = []
        try:
            bina = data_loader_binance.fetch_window(recent_start, end_ts, keyword=symbol)
        except Exception:
            bina = []
        sent_rows = merge_daily(fmp, bina)
        last_sent = sent_rows[-1] if sent_rows else {
            "sentiment_finbert": 0.0, "sentiment_emotion": 0.0,
            "news_volume": 0, "social_volume": 0,
        }

        closes = [r["close"] for r in market_rows]
        rets = _log_returns(closes)
        # Momentum = 5-bar return; volatility = std of last 10 returns.
        if len(closes) >= 6 and closes[-6] > 0:
            momentum = (closes[-1] - closes[-6]) / closes[-6]
        else:
            momentum = 0.0
        vol_window = rets[-10:]
        _, vol = _mean_std(vol_window)

        # Build z-scored history of momentum to scale the current value.
        momentum_hist: List[float] = []
        for i in range(6, len(closes)):
            denom = closes[i - 6]
            if denom > 0:
                momentum_hist.append((closes[i] - denom) / denom)

        signals = {
            "sentiment_finbert": float(last_sent.get("sentiment_finbert", 0.0)),
            "sentiment_emotion": float(last_sent.get("sentiment_emotion", 0.0)),
            "news_volume": float(last_sent.get("news_volume", 0)),
            "social_volume": float(last_sent.get("social_volume", 0)),
            "price_momentum": float(momentum),
            "volatility": float(vol),
        }
        oasis, oasis_coverage = _latest_oasis_features(cfg, norm_start, end_ts)
        signals.update(oasis)
        # z-score price_momentum vs its history; sentiment scores are already in [-1,1].
        signals_z = {
            "sentiment_finbert": signals["sentiment_finbert"],
            "sentiment_emotion": signals["sentiment_emotion"],
            "news_volume": math.log1p(signals["news_volume"]) / 5.0,
            "social_volume": math.log1p(signals["social_volume"]) / 5.0,
            "price_momentum": _zscored_signal(signals["price_momentum"], momentum_hist),
            "volatility": 0.0,  # vol enters the sim via sigma, not as direction
        }
        for key in OASIS_FACTOR_KEYS:
            signals_z[key] = float(oasis.get(key, 0.0))

        model_pred = predict_weighted([signals_z], weights, feature_keys)[0]
        score = float(model_pred.get("model_score", 0.0))
        p_up = float(model_pred.get("p_up", sigmoid(score)))
        # squash to [-1, 1] then scale to ±0.5% daily drift bump.
        squashed = math.tanh(score)
        bias = squashed * 0.005

        risk = float(oasis.get("oasis_risk_intensity", 0.0))
        disagreement = float(oasis.get("oasis_disagreement", 0.0))
        panic = float(oasis.get("oasis_panic_score", 0.0))
        pulse = float(oasis.get("oasis_pulse_score", 0.0))
        sigma_multiplier = _clip(1.0 + 0.35 * risk + 0.25 * disagreement + 0.25 * panic + 0.15 * pulse, 0.75, 1.8)

        return bias, sigma_multiplier, {
            "model_kind": cfg.get("model_kind", "weighted"),
            "forecast_head": "weighted_live_score",
            "ablation_mode": ablation_mode,
            "feature_keys": feature_keys,
            "score": score,
            "p_up": p_up,
            "confidence": round(abs(p_up - 0.5) * 2.0, 4),
            "feature_contribution": model_pred.get("feature_contribution") or {},
            "signals": signals,
            "signals_z": signals_z,
            "oasis_features": oasis,
            "oasis_coverage": oasis_coverage,
            "bias_per_day": bias,
            "sigma_multiplier": sigma_multiplier,
        }
    except Exception as exc:
        logger.warning("model bias failed: %s", exc)
        return 0.0, 1.0, {"error": str(exc)}


def forecast_weekly_distribution(
    symbol: str,
    *,
    spot_price: float,
    bins: List[Dict[str, Any]],
    anchor_date: datetime,
    horizon_days: int = 7,
    n_paths: int = 5000,
    history_days: int = 90,
    seed: Optional[int] = None,
    model_family: str = "price_point_calibrated_ml",
) -> Dict[str, Any]:
    """MC-sample terminal-price distribution and bucket into bins.

    The forecast direction/shape is driven by the selected `model_family`
    (see `model_registry`):
      - price_point_calibrated_ml → forward price distribution (Kronos+Chronos);
        primary bin probs are computed analytically (lognormal), with a Monte
        Carlo cross-check stored under each bin's `prob_mc`.
      - two_tower / financial_forecast → directional probability; bins are
        produced by biasing the Monte Carlo drift.

    Returns:
        {
          "bins": [{...bin, "prob", "prob_mc", "hit_prob", "count"}],
          "expected_price", "median_price", "spot_price", "n_paths",
          "model_meta": {...}, "model_debug": {...},
        }
    """
    end_ts = anchor_date.astimezone(timezone.utc)
    start_ts = end_ts - timedelta(days=history_days)
    market_rows = data_loader_market.fetch_ohlcv(symbol, "1d", start_ts, end_ts)
    closes = [r["close"] for r in market_rows]
    rets = _log_returns(closes)
    mu, sigma = _mean_std(rets)
    # Floor sigma to avoid degenerate forecasts when history is too short.
    sigma = max(sigma, 0.005)

    spec = resolve_model(model_family)
    model_key = spec["key"]

    # --- Forward inference from the selected model -----------------------
    forward = forward_forecast(symbol, model_key, market_rows, horizon=horizon_days)
    forward_kind = forward.get("kind", "direction")

    # Translate the forward forecast into Monte-Carlo drift + sigma.
    if forward_kind == "price_dist" and forward.get("p50"):
        z80 = 1.2815515655446004
        p10 = max(float(forward["p10"]), 1e-9)
        p50 = max(float(forward["p50"]), 1e-9)
        p90 = max(float(forward["p90"]), 1e-9)
        lo, hi = min(p10, p90), max(p10, p90)
        total_drift = math.log(p50 / spot_price) if spot_price > 0 else 0.0
        total_sigma = (math.log(hi) - math.log(lo)) / (2.0 * z80)
        bias_per_day = total_drift / max(horizon_days, 1)
        adjusted_sigma = max(0.001, total_sigma / math.sqrt(max(horizon_days, 1)))
        sigma_multiplier = adjusted_sigma / sigma if sigma > 0 else 1.0
        debug = {
            "forecast_head": "forward_price_distribution",
            "model_kind": model_key,
            "mode": forward.get("mode"),
            "p_up": forward.get("p_up"),
            "p10": p10, "p50": p50, "p90": p90,
            "predicted_price": forward.get("predicted_price"),
            "calibration_applied": forward.get("calibration_applied"),
            "warning": forward.get("warning"),
            "bias_per_day": bias_per_day,
            "sigma_multiplier": sigma_multiplier,
        }
    else:
        # Directional model → convert p_up into a daily drift bump (±0.5%/day).
        p_up = float(forward.get("p_up", 0.5))
        signal = max(-1.0, min(1.0, (p_up - 0.5) * 2.0))
        bias_per_day = signal * 0.005
        # Still widen sigma for crowded-risk regimes using OASIS multiplier.
        _, sigma_multiplier, oasis_debug = _build_model_bias(symbol, end_ts)
        adjusted_sigma = max(0.001, sigma * sigma_multiplier)
        debug = {
            "forecast_head": "forward_directional",
            "model_kind": model_key,
            "mode": forward.get("mode"),
            "p_up": p_up,
            "signal": signal,
            "warning": forward.get("warning"),
            "bias_per_day": bias_per_day,
            "sigma_multiplier": sigma_multiplier,
            "oasis_debug": oasis_debug,
        }

    rng = random.Random(seed)

    counts = [0] * len(bins)
    overflow = 0
    terminal_prices: List[float] = []
    path_maxes: List[float] = []
    for _ in range(n_paths):
        price = spot_price
        path_max = spot_price
        for _ in range(horizon_days):
            shock = rng.gauss(mu + bias_per_day, adjusted_sigma)
            price *= math.exp(shock)
            if price > path_max:
                path_max = price
        terminal_prices.append(price)
        path_maxes.append(path_max)
        idx = assign_bin(price, bins)
        if idx is None:
            overflow += 1
        else:
            counts[idx] += 1

    total = max(n_paths, 1)
    mc_probs = [c / total for c in counts]

    # Primary probabilities: analytic lognormal for price_dist, MC otherwise.
    if forward_kind == "price_dist" and forward.get("p50"):
        primary_probs = lognormal_bin_probabilities(
            bins, p10=forward["p10"], p50=forward["p50"], p90=forward["p90"],
        )
    else:
        primary_probs = mc_probs

    # Cumulative-touch probability: P(weekly high reaches the bin's lower edge).
    # Aligns with Polymarket "what price will BTC hit" semantics for upper tiers.
    bin_out = []
    for b, c, prob, prob_mc in zip(bins, counts, primary_probs, mc_probs):
        bb = dict(b)
        bb["prob"] = round(float(prob), 4)
        bb["prob_mc"] = round(float(prob_mc), 4)
        bb["count"] = c
        lo = b.get("low")
        if lo is not None and lo >= spot_price and path_maxes:
            hits = sum(1 for pm in path_maxes if pm >= lo)
            bb["hit_prob"] = round(hits / total, 4)
        else:
            bb["hit_prob"] = None
        bin_out.append(bb)

    terminal_prices.sort()
    median = terminal_prices[len(terminal_prices) // 2] if terminal_prices else spot_price
    expected = sum(terminal_prices) / max(len(terminal_prices), 1)

    model_meta = {
        "model_family": model_key,
        "label": spec.get("label_en"),
        "label_zh": spec.get("label_zh"),
        "output_kind": forward_kind,
        "mode": forward.get("mode"),
        "p_up": forward.get("p_up"),
        "calibration_applied": forward.get("calibration_applied", False),
        "warning": forward.get("warning"),
    }

    return {
        "bins": bin_out,
        "expected_price": round(expected, 2),
        "median_price": round(median, 2),
        "spot_price": spot_price,
        "n_paths": n_paths,
        "horizon_days": horizon_days,
        "history_mu_daily": round(mu, 6),
        "history_sigma_daily": round(sigma, 6),
        "adjusted_sigma_daily": round(adjusted_sigma, 6),
        "bias_per_day": round(bias_per_day, 6),
        "sigma_adjustment": {
            "multiplier": round(sigma_multiplier, 4),
            "base_sigma_daily": round(sigma, 6),
            "adjusted_sigma_daily": round(adjusted_sigma, 6),
        },
        "overflow_paths": overflow,
        "model_meta": model_meta,
        "model_debug": debug,
        "strategy_cfg": get_active_strategy_cfg(symbol),
    }


def fetch_spot_price(symbol: str) -> Optional[float]:
    """Return the most recent close for `symbol` (1h interval, last 24h)."""
    end = datetime.now(timezone.utc)
    rows = data_loader_market.fetch_ohlcv(symbol, "1h", end - timedelta(hours=24), end)
    if not rows:
        # Fallback to daily.
        rows = data_loader_market.fetch_ohlcv(symbol, "1d", end - timedelta(days=7), end)
    if not rows:
        return None
    return float(rows[-1]["close"])
