"""Technical multi-indicator signal and optional LLM assessor for stocks."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from ...utils.llm_client import LLMClient

logger = logging.getLogger("finrex.financial.technical_llm_signal")

BIAS_STD_WINDOW = 252
PARTIAL_MIN_BARS = 150
FULL_MIN_BARS = 260
DEFAULT_LLM_CACHE_TTL_SECONDS = 21600

LEVEL_SCORES: Dict[str, float] = {
    "strong_bullish": 1.0,
    "bullish": 0.5,
    "neutral": 0.0,
    "bearish": -0.5,
    "strong_bearish": -1.0,
}

_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def technical_llm_enabled() -> bool:
    return _env_bool("STOCK_TECH_LLM_ENABLED", False)


def clear_llm_cache() -> None:
    _CACHE.clear()


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        out = float(value)
        return out if math.isfinite(out) else default
    except (TypeError, ValueError):
        return default


def _clamp(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def _ema(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    k = 2.0 / (period + 1)
    out = [values[0]]
    for value in values[1:]:
        out.append(value * k + out[-1] * (1.0 - k))
    return out


def compute_rsi(closes: List[float], period: int = 6) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(-period, 0)]
    gains = [delta if delta > 0 else 0.0 for delta in deltas]
    losses = [-delta if delta < 0 else 0.0 for delta in deltas]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def compute_bias_std(closes: List[float], sma_period: int, std_window: int = BIAS_STD_WINDOW) -> float:
    if len(closes) < sma_period:
        return 0.0
    sma = sum(closes[-sma_period:]) / sma_period
    bias = (closes[-1] - sma) / sma if sma else 0.0

    effective_window = min(std_window, len(closes))
    bias_history: List[float] = []
    for idx in range(len(closes) - effective_window, len(closes)):
        if idx < sma_period - 1:
            continue
        window = closes[idx - sma_period + 1: idx + 1]
        mean = sum(window) / sma_period
        bias_history.append((closes[idx] - mean) / mean if mean else 0.0)
    if not bias_history:
        return 0.0

    mean_bias = sum(bias_history) / len(bias_history)
    variance = sum((item - mean_bias) ** 2 for item in bias_history) / len(bias_history)
    std_bias = variance ** 0.5
    return bias / std_bias if std_bias > 0 else 0.0


def compute_macd_hist_pct(closes: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> float:
    if len(closes) < slow + signal:
        return 0.0
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    dif_series = [fast_v - slow_v for fast_v, slow_v in zip(ema_fast, ema_slow)]
    dea_series = _ema(dif_series, signal)
    hist = dif_series[-1] - dea_series[-1]
    price = closes[-1] if closes[-1] else 1.0
    return hist / price


def compute_volume_ratio(volumes: List[float], period: int = 20) -> float:
    if len(volumes) < period + 1:
        return 1.0
    avg = sum(volumes[-(period + 1):-1]) / period
    if avg <= 0:
        return 1.0
    return volumes[-1] / avg


def compute_atr_pct(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 0.0
    true_ranges: List[float] = []
    for idx in range(-period, 0):
        high = highs[idx]
        low = lows[idx]
        prev_close = closes[idx - 1]
        true_ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    atr = sum(true_ranges) / period
    price = closes[-1] if closes[-1] else 1.0
    return atr / price * 100.0


def _classify_ascending(value: float, thresholds: Tuple[float, float, float, float]) -> str:
    if value < thresholds[0]:
        return "strong_bullish"
    if value < thresholds[1]:
        return "bullish"
    if value < thresholds[2]:
        return "neutral"
    if value < thresholds[3]:
        return "bearish"
    return "strong_bearish"


def _classify_descending(value: float, thresholds: Tuple[float, float, float, float]) -> str:
    if value > thresholds[3]:
        return "strong_bullish"
    if value > thresholds[2]:
        return "bullish"
    if value > thresholds[1]:
        return "neutral"
    if value > thresholds[0]:
        return "bearish"
    return "strong_bearish"


def classify_indicator(name: str, value: float) -> str:
    if name == "RSI_6":
        return _classify_descending(value, (20.0, 40.0, 60.0, 80.0))
    if name.startswith("BIAS_"):
        return _classify_descending(value, (-2.0, -1.0, 1.0, 2.0))
    if name == "MACD_HIST_PCT":
        return _classify_descending(value, (-0.02, -0.005, 0.005, 0.02))
    if name == "VOL_RATIO_20":
        return _classify_descending(value, (0.5, 0.7, 1.5, 2.0))
    if name == "ATR_PCT_14":
        return _classify_ascending(value, (1.0, 2.0, 4.0, 6.0))
    return "neutral"


def _clean_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, float]]:
    clean: List[Dict[str, float]] = []
    for row in rows or []:
        close = _safe_float(row.get("close"))
        if close is None or close <= 0:
            continue
        open_ = _safe_float(row.get("open"), close) or close
        high = _safe_float(row.get("high"), close) or close
        low = _safe_float(row.get("low"), close) or close
        volume = _safe_float(row.get("volume"), 0.0) or 0.0
        clean.append({
            "open": open_,
            "high": max(high, low, close),
            "low": min(high, low, close),
            "close": close,
            "volume": max(0.0, volume),
        })
    return clean


def build_technical_signal(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    clean = _clean_rows(rows)
    bars = len(clean)
    if bars < PARTIAL_MIN_BARS:
        return {
            "ok": False,
            "status": "insufficient_history",
            "bars": bars,
            "required_bars": PARTIAL_MIN_BARS,
            "multi_indicator_score": 0.0,
            "indicators": {},
        }

    closes = [row["close"] for row in clean]
    highs = [row["high"] for row in clean]
    lows = [row["low"] for row in clean]
    volumes = [row["volume"] for row in clean]
    values = {
        "RSI_6": compute_rsi(closes, 6),
        "BIAS_20": compute_bias_std(closes, 20, BIAS_STD_WINDOW),
        "BIAS_60": compute_bias_std(closes, 60, BIAS_STD_WINDOW),
        "BIAS_120": compute_bias_std(closes, 120, BIAS_STD_WINDOW),
        "MACD_HIST_PCT": compute_macd_hist_pct(closes),
        "VOL_RATIO_20": compute_volume_ratio(volumes, 20),
        "ATR_PCT_14": compute_atr_pct(highs, lows, closes, 14),
    }
    indicators: Dict[str, Dict[str, Any]] = {}
    for name, value in values.items():
        level = classify_indicator(name, value)
        indicators[name] = {
            "value": round(value, 6),
            "level": level,
            "score": LEVEL_SCORES[level],
        }
    weights = {
        "RSI_6": 0.8,
        "BIAS_20": 0.6,
        "BIAS_60": 0.6,
        "BIAS_120": 0.6,
        "MACD_HIST_PCT": 1.0,
        "VOL_RATIO_20": 0.6,
        "ATR_PCT_14": 0.5,
    }
    total = sum(weights.values()) or 1.0
    raw_score = sum(indicators[name]["score"] * weights[name] for name in indicators) / total
    score = _clamp(raw_score)
    return {
        "ok": True,
        "status": "full" if bars >= FULL_MIN_BARS else "partial",
        "bars": bars,
        "required_bars": FULL_MIN_BARS,
        "bias_std_window": BIAS_STD_WINDOW,
        "multi_indicator_score": round(score, 4),
        "indicators": indicators,
    }


def _last_row_date(rows: List[Dict[str, Any]]) -> str:
    for row in reversed(rows or []):
        raw = row.get("date") or row.get("datetime") or row.get("timestamp")
        if raw not in (None, ""):
            return str(raw)[:32]
    return ""


def _indicator_hash(technical_signal: Dict[str, Any]) -> str:
    payload = {
        "score": technical_signal.get("multi_indicator_score"),
        "indicators": technical_signal.get("indicators") or {},
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _cache_key(symbol: str, rows: List[Dict[str, Any]], horizon_days: int, technical_signal: Dict[str, Any]) -> str:
    return "|".join([
        (symbol or "").strip().upper(),
        _last_row_date(rows),
        str(max(1, int(horizon_days or 1))),
        _indicator_hash(technical_signal),
    ])


def _cache_ttl_seconds() -> int:
    raw = os.environ.get("STOCK_TECH_LLM_CACHE_TTL_SECONDS")
    try:
        return max(0, int(raw)) if raw not in (None, "") else DEFAULT_LLM_CACHE_TTL_SECONDS
    except ValueError:
        return DEFAULT_LLM_CACHE_TTL_SECONDS


def _normalize_llm_result(data: Dict[str, Any]) -> Dict[str, Any]:
    score = _safe_float(data.get("score"))
    if score is None:
        raise ValueError("missing numeric score")
    confidence = str(data.get("confidence") or "low").strip().lower()
    if confidence not in {"low", "medium", "high"}:
        conf_num = _safe_float(data.get("confidence"))
        if conf_num is not None:
            confidence = "high" if conf_num >= 0.7 else ("medium" if conf_num >= 0.4 else "low")
        else:
            confidence = "low"
    risk_flags_raw = data.get("risk_flags") or []
    risk_flags = [str(item)[:160] for item in risk_flags_raw if str(item).strip()] if isinstance(risk_flags_raw, list) else []
    return {
        "ok": True,
        "enabled": True,
        "score": round(_clamp(score), 4),
        "confidence": confidence,
        "reason": str(data.get("reason") or "")[:500],
        "risk_flags": risk_flags[:8],
        "source": "llm",
    }


def _build_messages(symbol: str, horizon_days: int, technical_signal: Dict[str, Any]) -> List[Dict[str, str]]:
    compact = {
        "symbol": symbol,
        "horizon_days": horizon_days,
        "multi_indicator_score": technical_signal.get("multi_indicator_score"),
        "quality": technical_signal.get("status"),
        "bars": technical_signal.get("bars"),
        "indicators": technical_signal.get("indicators") or {},
    }
    return [
        {
            "role": "system",
            "content": (
                "You are a quantitative equity signal reviewer. Return only JSON. "
                "Do not provide price targets, trade actions, position sizing, or investment advice."
            ),
        },
        {
            "role": "user",
            "content": (
                "Assess whether these technical indicators support next-horizon upside or downside. "
                "Return JSON with keys: score (-1 to 1), confidence (low|medium|high), "
                "reason (brief), risk_flags (array of strings). Data:\n"
                f"{json.dumps(compact, ensure_ascii=False, sort_keys=True)}"
            ),
        },
    ]


def call_technical_llm_signal(
    symbol: str,
    rows: List[Dict[str, Any]],
    horizon_days: int,
    technical_signal: Dict[str, Any],
    llm_client: Optional[Any] = None,
) -> Dict[str, Any]:
    if not technical_llm_enabled():
        return {"ok": False, "enabled": False, "reason": "STOCK_TECH_LLM_ENABLED=false"}
    if not technical_signal.get("ok"):
        return {"ok": False, "enabled": True, "reason": "technical signal unavailable"}

    key = _cache_key(symbol, rows, horizon_days, technical_signal)
    ttl = _cache_ttl_seconds()
    now = time.time()
    cached = _CACHE.get(key)
    if cached and ttl > 0 and now - cached[0] <= ttl:
        out = dict(cached[1])
        out["cache_hit"] = True
        return out

    try:
        client = llm_client
        if client is None:
            model_override = os.environ.get("STOCK_TECH_LLM_MODEL") or None
            client = LLMClient(
                model=model_override,
                deployment_name=model_override if model_override else None,
            )
        data = client.chat_json(
            messages=_build_messages(symbol, horizon_days, technical_signal),
            temperature=0.1,
            max_tokens=500,
        )
        out = _normalize_llm_result(data)
    except Exception as exc:  # noqa: BLE001
        logger.warning("technical LLM signal failed for %s: %s", symbol, exc)
        out = {"ok": False, "enabled": True, "reason": f"technical LLM signal failed: {exc}"}

    if out.get("ok"):
        _CACHE[key] = (now, dict(out))
    out["cache_hit"] = False
    return out
