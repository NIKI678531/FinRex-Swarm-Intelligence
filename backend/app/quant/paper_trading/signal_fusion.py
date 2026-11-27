"""Multi-source signal fusion for the auto paper-trader.

Aggregates the heterogeneous outputs of several forecasters into a single
normalized, confidence-weighted directional view per symbol:

* Quant pipeline      — ``pipeline.latest_signal`` (``signal_hybrid`` / ``p_meta``)
* Stock forecaster    — ``StockForecastService.forecast`` (``composite`` / ``confidence_score``)
* Crypto forecaster   — ``CryptoForecastService.forecast`` (``composite`` / ``confidence_score``)

Each contributing source is reduced to:
    score      in [-1, 1]  (positive = bullish)
    confidence in [0, 1]

The fused score is a confidence-weighted mean of the source scores; the fused
confidence is the mean source confidence scaled by a directional-agreement
ratio so conflicting signals self-attenuate.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..data import symbol_registry

logger = logging.getLogger(__name__)

_CRYPTO_CLASSES = {"crypto"}
_STOCK_CLASSES = {"us_stock", "hk_stock", "hk_etf", "a_stock"}


def _clamp(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _direction_label(score: float, eps: float = 1e-6) -> str:
    if score > eps:
        return "up"
    if score < -eps:
        return "down"
    return "neutral"


# ---------------------------------------------------------------------------
# Per-source extractors → {score, confidence} or None when unavailable
# ---------------------------------------------------------------------------
def _from_pipeline(symbol: str) -> Optional[Dict[str, Any]]:
    try:
        from .. import pipeline

        sig = pipeline.latest_signal(symbol)
    except FileNotFoundError:
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("pipeline signal failed for %s: %s", symbol, exc)
        return None
    if not sig:
        return None

    score = _safe_float(sig.get("signal_hybrid"))
    if score is None:
        score = _safe_float(sig.get("signal_swarm"))
    p_meta = _safe_float(sig.get("p_meta"))
    if score is None and p_meta is None:
        return None
    if score is None:
        score = (p_meta - 0.5) * 2.0
    score = _clamp(score)

    if p_meta is not None:
        confidence = abs(p_meta - 0.5) * 2.0
    else:
        confidence = abs(score)
    return {
        "name": "quant_pipeline",
        "score": score,
        "confidence": _clamp(confidence, 0.0, 1.0),
        "raw": {"signal_hybrid": sig.get("signal_hybrid"), "p_meta": p_meta,
                "run_id": sig.get("run_id"), "ts": sig.get("ts")},
    }


def _from_forecast(name: str, result: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not result or not result.get("ok"):
        return None
    breakdown = result.get("score_breakdown") or {}
    score = _safe_float(breakdown.get("composite"))
    if score is None:
        # Fall back to direction sign when composite is missing.
        direction = result.get("direction")
        score = {"up": 0.5, "down": -0.5}.get(direction, 0.0)
    score = _clamp(score)
    confidence = _safe_float(result.get("confidence_score"))
    if confidence is None:
        prob = _safe_float(result.get("probability"))
        confidence = abs(prob - 0.5) * 2.0 if prob is not None else abs(score)
    return {
        "name": name,
        "score": score,
        "confidence": _clamp(confidence, 0.0, 1.0),
        "raw": {"direction": result.get("direction"),
                "probability": result.get("probability"),
                "confidence_score": result.get("confidence_score")},
    }


def _crypto_signal(symbol: str) -> Optional[Dict[str, Any]]:
    try:
        from app.services.financial.crypto_forecast_service import CryptoForecastService

        result = CryptoForecastService().forecast(symbol=symbol, horizon="1d", include_news=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("crypto forecast failed for %s: %s", symbol, exc)
        return None
    return _from_forecast("crypto_forecast", result)


def _stock_signal(symbol: str) -> Optional[Dict[str, Any]]:
    try:
        from app.services.financial.stock_forecast_service import StockForecastService

        result = StockForecastService().forecast(symbol=symbol, horizon_days=1)
    except Exception as exc:  # noqa: BLE001
        logger.warning("stock forecast failed for %s: %s", symbol, exc)
        return None
    return _from_forecast("stock_forecast", result)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def collect_sources(symbol: str) -> List[Dict[str, Any]]:
    """Gather every applicable normalized signal for ``symbol``."""
    sources: List[Dict[str, Any]] = []

    pipeline_sig = _from_pipeline(symbol)
    if pipeline_sig:
        sources.append(pipeline_sig)

    try:
        asset_class = symbol_registry.get(symbol).asset_class
    except KeyError:
        asset_class = None

    if asset_class in _CRYPTO_CLASSES:
        crypto = _crypto_signal(symbol)
        if crypto:
            sources.append(crypto)
    elif asset_class in _STOCK_CLASSES:
        stock = _stock_signal(symbol)
        if stock:
            sources.append(stock)

    return sources


def fuse(symbol: str) -> Dict[str, Any]:
    """Fuse all available signals for ``symbol`` into one directional view."""
    sources = collect_sources(symbol)
    if not sources:
        return {
            "symbol": symbol,
            "ok": False,
            "reason": "no signal sources available",
            "fused_score": 0.0,
            "fused_confidence": 0.0,
            "direction": "neutral",
            "sources": [],
        }

    total_conf = sum(s["confidence"] for s in sources)
    if total_conf <= 0:
        fused_score = sum(s["score"] for s in sources) / len(sources)
    else:
        fused_score = sum(s["score"] * s["confidence"] for s in sources) / total_conf
    fused_score = _clamp(fused_score)

    # Directional agreement (confidence-weighted) attenuates conflicting views.
    fused_dir = _direction_label(fused_score)
    if fused_dir == "neutral" or total_conf <= 0:
        agreement = 0.0
    else:
        aligned = sum(
            s["confidence"] for s in sources
            if _direction_label(s["score"]) == fused_dir
        )
        agreement = aligned / total_conf

    mean_conf = total_conf / len(sources)
    fused_confidence = _clamp(mean_conf * agreement, 0.0, 1.0)

    return {
        "symbol": symbol,
        "ok": True,
        "fused_score": round(fused_score, 4),
        "fused_confidence": round(fused_confidence, 4),
        "direction": fused_dir,
        "agreement": round(agreement, 4),
        "n_sources": len(sources),
        "sources": [
            {
                "name": s["name"],
                "score": round(s["score"], 4),
                "confidence": round(s["confidence"], 4),
                "direction": _direction_label(s["score"]),
                "raw": s.get("raw"),
            }
            for s in sources
        ],
    }
