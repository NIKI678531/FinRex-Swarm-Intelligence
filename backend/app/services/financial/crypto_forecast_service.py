"""Structured crypto directional forecast service.

This service gives the Financial OIF report a deterministic forecast backbone:
market indicators + observed comments/news + optional derivatives facts. LLMs
can explain this result, but the direction is computed here.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..asset_forecast.signal_engine import compute_signals
from ..prediction_clock import build_time_anchor
from .crypto_market_provider import CryptoMarketProvider, normalize_crypto_symbol
from .news_provider import NewsProvider
from .sentiment_provider import SentimentProvider

logger = logging.getLogger("finrex.financial.crypto_forecast_service")


def _clamp(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_horizon(value: Any, default: int = 1) -> int:
    """Parse a forecast horizon string into number of days.

    Default is 1d to align with the Polymarket daily BTC market
    (resolves at 12:00 UTC every day).
    """
    if value is None or value == "":
        return default
    s = str(value).strip().lower()
    mapping = {
        "1d": 1, "daily": 1, "intraday": 1, "today": 1, "tomorrow": 1,
        "1w": 7, "week": 7, "7d": 7, "5d": 5, "2w": 14, "1m": 30,
    }
    if s in mapping:
        return mapping[s]
    try:
        return max(1, min(60, int(s)))
    except Exception:
        return default


def _as_text(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return str(item.get("text") or item.get("content") or item.get("comment") or item.get("body") or "").strip()
    return ""


def _normalize_items(items: Optional[List[Any]], kind: str, default_site: str) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    if not isinstance(items, list):
        return normalized
    for idx, item in enumerate(items):
        if isinstance(item, str):
            text = item.strip()
            if not text:
                continue
            normalized.append({
                "title": f"{kind} #{idx + 1}",
                "text": text,
                "site": default_site,
                "published_at": datetime.now().isoformat(),
                "like_count": 0,
                "reply_count": 0,
                "source": default_site,
            })
            continue
        if not isinstance(item, dict):
            continue
        text = _as_text(item)
        title = str(item.get("title") or f"{kind} #{idx + 1}").strip()
        if not text and not title:
            continue
        normalized.append({
            "title": title,
            "text": text or title,
            "url": item.get("url") or item.get("link") or "",
            "site": item.get("site") or item.get("source") or default_site,
            "published_at": item.get("published_at") or item.get("created_at") or item.get("date") or "",
            "tickers": item.get("tickers") or "",
            "like_count": _safe_float(item.get("like_count") or item.get("likes") or 0, 0.0) or 0.0,
            "reply_count": _safe_float(item.get("reply_count") or item.get("replies") or 0, 0.0) or 0.0,
            "post_id": item.get("post_id") or item.get("source_article_id") or item.get("id") or "",
            "source": item.get("source") or default_site,
        })
    return normalized


def _parse_time(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):
            ts = float(value)
            if ts > 10_000_000_000:
                ts /= 1000
            return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
        s = str(value).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt.replace(tzinfo=None)
    except Exception:
        return None


def _item_weight(item: Dict[str, Any]) -> float:
    weight = 1.0
    likes = _safe_float(item.get("like_count"), 0.0) or 0.0
    replies = _safe_float(item.get("reply_count"), 0.0) or 0.0
    weight += min(2.0, math.log1p(max(0.0, likes)) / 4.0)
    weight += min(1.0, math.log1p(max(0.0, replies)) / 5.0)
    dt = _parse_time(item.get("published_at") or item.get("created_at"))
    if dt:
        age_days = max(0.0, (datetime.now() - dt).total_seconds() / 86400)
        if age_days <= 3:
            weight += 0.5
        elif age_days <= 7:
            weight += 0.25
    return weight


def _weighted_sentiment(sentiment_result: Dict[str, Any]) -> Dict[str, Any]:
    scored = sentiment_result.get("scored_items") or []
    if not scored:
        return {**sentiment_result.get("summary", {}), "weighted_avg_compound": 0.0, "weighted_count": 0.0}
    weighted_sum = 0.0
    weight_total = 0.0
    for item in scored:
        compound = _safe_float((item.get("sentiment") or {}).get("compound"), 0.0) or 0.0
        weight = _item_weight(item)
        weighted_sum += compound * weight
        weight_total += weight
    weighted_avg = weighted_sum / weight_total if weight_total else 0.0
    summary = dict(sentiment_result.get("summary") or {})
    summary["weighted_avg_compound"] = round(weighted_avg, 4)
    summary["weighted_count"] = round(weight_total, 3)
    return summary


def _direction_from_composite(score: float) -> str:
    if score > 0.18:
        return "bullish"
    if score < -0.18:
        return "bearish"
    return "neutral"


def _confidence_label(value: float) -> str:
    if value >= 0.70:
        return "high"
    if value >= 0.45:
        return "medium"
    return "low"


def _technical_factor(signal: Dict[str, Any]) -> float:
    if not signal.get("ok"):
        return 0.0
    score = _safe_float(signal.get("score"), 0.0) or 0.0
    return _clamp(score / 6.0)


def _volume_factor(rows: List[Dict[str, Any]]) -> float:
    if len(rows) < 22:
        return 0.0
    last = rows[-1]
    prev = rows[-2]
    avg_vol = sum(float(r.get("volume") or 0.0) for r in rows[-21:-1]) / 20.0
    last_vol = float(last.get("volume") or 0.0)
    if avg_vol <= 0 or last_vol < avg_vol * 1.35:
        return 0.0
    last_close = float(last.get("close") or 0.0)
    prev_close = float(prev.get("close") or 0.0)
    if prev_close <= 0:
        return 0.0
    ret = last_close / prev_close - 1.0
    if ret > 0.01:
        return 0.18
    if ret < -0.01:
        return -0.18
    return 0.0


def _derivatives_factor(derivatives: Dict[str, Any]) -> Tuple[float, List[str]]:
    warnings: List[str] = []
    if not derivatives.get("ok"):
        return 0.0, warnings
    funding = derivatives.get("funding") or []
    latest = None
    for item in reversed(funding):
        latest = _safe_float(item.get("funding_rate"))
        if latest is not None:
            break
    factor = 0.0
    if latest is not None:
        if latest > 0.001:
            factor -= 0.20
            warnings.append("Funding rate is elevated; long positioning may be crowded.")
        elif latest < -0.0005:
            factor += 0.15
            warnings.append("Funding rate is negative; short positioning may be crowded.")
    return _clamp(factor), warnings


def _build_target_range(last_close: Optional[float], expected_return_pct: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not last_close or not expected_return_pct:
        return None
    central = _safe_float(expected_return_pct.get("central"), 0.0) or 0.0
    lower = _safe_float(expected_return_pct.get("lower"), 0.0) or 0.0
    upper = _safe_float(expected_return_pct.get("upper"), 0.0) or 0.0
    return {
        "low": round(last_close * (1.0 + lower / 100.0), 4),
        "mid": round(last_close * (1.0 + central / 100.0), 4),
        "high": round(last_close * (1.0 + upper / 100.0), 4),
    }


def _build_precise_fallback(
    last_close: Optional[float],
    target_range: Optional[Dict[str, Any]],
    horizon_days: int,
    reason: str,
) -> Optional[Dict[str, Any]]:
    """Return a deterministic precise-price fallback when foundation models are unavailable."""
    if target_range:
        low = _safe_float(target_range.get("low"))
        mid = _safe_float(target_range.get("mid"))
        high = _safe_float(target_range.get("high"))
        predicted = mid if mid is not None else ((low + high) / 2.0 if low is not None and high is not None else None)
        if predicted is not None:
            return {
                "predicted_price": round(predicted, 4),
                "p10": round(low if low is not None else predicted, 4),
                "p50": round(predicted, 4),
                "p90": round(high if high is not None else predicted, 4),
                "p_up": None if last_close in (None, 0) else round(1.0 if predicted > float(last_close) else 0.0, 4),
                "expected_return": None if last_close in (None, 0) else round(predicted / float(last_close) - 1.0, 6),
                "uncertainty": None,
                "cross_model_agreement": None,
                "mode": "technical_range_fallback",
                "horizon_days": horizon_days,
                "last_close": last_close,
                "source": "target_price_range_midpoint",
                "warning": reason,
            }
    if last_close:
        band = float(last_close) * 0.02
        return {
            "predicted_price": round(float(last_close), 4),
            "p10": round(float(last_close) - band, 4),
            "p50": round(float(last_close), 4),
            "p90": round(float(last_close) + band, 4),
            "p_up": 0.5,
            "expected_return": 0.0,
            "uncertainty": None,
            "cross_model_agreement": None,
            "mode": "last_close_fallback",
            "horizon_days": horizon_days,
            "last_close": last_close,
            "source": "last_close_plus_minus_2pct",
            "warning": reason,
        }
    return None


class CryptoForecastService:
    """Build a one-week crypto directional forecast."""

    def __init__(
        self,
        market_provider: Optional[CryptoMarketProvider] = None,
        sentiment_provider: Optional[SentimentProvider] = None,
        news_provider: Optional[NewsProvider] = None,
    ):
        self.market_provider = market_provider or CryptoMarketProvider()
        self.sentiment_provider = sentiment_provider or SentimentProvider()
        self.news_provider = news_provider or NewsProvider()

    def forecast(
        self,
        symbol: str = "BTC",
        horizon: Any = "1d",
        comments: Optional[List[Any]] = None,
        articles: Optional[List[Any]] = None,
        include_news: bool = True,
    ) -> Dict[str, Any]:
        normalized = normalize_crypto_symbol(symbol)
        horizon_days = _parse_horizon(horizon)
        warnings: List[str] = []

        market = self.market_provider.fetch_market(normalized["base"], limit=180)
        rows = market.get("ohlcv") or []
        warnings.extend(market.get("warnings") or [])
        signal = compute_signals(rows, horizon_days=min(max(horizon_days, 1), 30)) if rows else {"ok": False, "reason": "no_market_data"}

        comment_items = _normalize_items(comments, "Observed comment", "binance")
        article_items = _normalize_items(articles, "Selected article", "selected_seed")
        news_items: List[Dict[str, Any]] = []
        news_status: Dict[str, Any] = {"ok": False, "source": "none"}
        if include_news:
            news_status = self.news_provider.fetch_news(normalized["base"], asset_type="crypto", limit=20)
            news_items = news_status.get("items") or []
            if not news_status.get("ok"):
                if article_items:
                    warnings.append("Remote crypto news unavailable; using selected Step1 seed articles.")
                else:
                    warnings.append(f"Crypto news unavailable: {news_status.get('error') or 'empty'}")

        corpus = news_items + article_items + comment_items
        sentiment = self.sentiment_provider.score_corpus(corpus)
        sentiment_summary = _weighted_sentiment(sentiment)

        tech_factor = _technical_factor(signal)
        sentiment_factor = _clamp(float(sentiment_summary.get("weighted_avg_compound") or 0.0) * 1.6)
        volume_factor = _volume_factor(rows)
        derivatives_factor, derivative_warnings = _derivatives_factor(market.get("derivatives") or {})
        warnings.extend(derivative_warnings)

        factors = {
            "technical": tech_factor,
            "sentiment": sentiment_factor,
            "volume": volume_factor,
            "derivatives": derivatives_factor,
        }
        available_weights = {
            "technical": 0.55 if signal.get("ok") else 0.0,
            "sentiment": 0.30 if sentiment.get("ok") else 0.0,
            "volume": 0.07 if rows else 0.0,
            "derivatives": 0.08 if (market.get("derivatives") or {}).get("ok") else 0.0,
        }
        weight_total = sum(available_weights.values())
        weights = {k: (v / weight_total if weight_total else 0.0) for k, v in available_weights.items()}
        composite = sum(factors[k] * weights[k] for k in factors)

        sentiment_count = int(sentiment_summary.get("count") or 0)
        insufficient = not signal.get("ok") and sentiment_count < 5
        if insufficient:
            direction = "neutral"
            probability = 0.5
            confidence_value = 0.15
            status = "insufficient_data"
            warnings.append("Market data and observed sentiment are insufficient for a directional call.")
        else:
            direction = _direction_from_composite(composite)
            probability = round(max(0.15, min(0.85, 0.5 + composite * 0.32)), 4)
            agreement_bonus = 0.10 if signal.get("ok") and sentiment.get("ok") and tech_factor * sentiment_factor > 0 else 0.0
            confidence_value = min(0.95, max(0.20, abs(composite) * 0.65 + sum(available_weights.values()) * 0.25 + agreement_bonus))
            if sentiment_count < 5:
                confidence_value *= 0.75
                warnings.append("Observed sentiment sample is small (<5).")
            status = "ok"

        last_close = _safe_float(signal.get("last_close")) or _safe_float((market.get("ticker") or {}).get("last_price"))
        target_range = _build_target_range(last_close, signal.get("expected_return_pct") if signal.get("ok") else None)

        # Phase 3 — augment with foundation-model precise forecast (Kronos + Chronos)
        # Preserves target_price_range; adds new precise_forecast field only.
        precise_forecast = None
        precise_ohlcv_df = None
        foundation_warning = "Kronos/Chronos-Bolt unavailable; using deterministic range midpoint."
        try:
            if rows and len(rows) >= 32:
                import pandas as _pd
                from ...quant.models.foundation_ensemble import predict_ensemble, summarize_unavailable_reason  # type: ignore
                ohlcv_df = _pd.DataFrame([
                    {
                        "open": _safe_float(r.get("open"), r.get("close")),
                        "high": _safe_float(r.get("high"), r.get("close")),
                        "low": _safe_float(r.get("low"), r.get("close")),
                        "close": _safe_float(r.get("close")),
                        "volume": _safe_float(r.get("volume"), 0.0) or 0.0,
                    }
                    for r in rows
                ]).dropna(subset=["close"])
                precise_ohlcv_df = ohlcv_df
                fe = predict_ensemble(ohlcv_df, horizon=max(1, min(horizon_days, 14)))
                if fe:
                    precise_forecast = {
                        "predicted_price": fe.get("predicted_price"),
                        "p10": fe.get("p10"),
                        "p50": fe.get("p50"),
                        "p90": fe.get("p90"),
                        "p_up": fe.get("p_up"),
                        "expected_return": fe.get("expected_return"),
                        "uncertainty": fe.get("foundation_uncertainty"),
                        "cross_model_agreement": fe.get("cross_model_agreement"),
                        "mode": fe.get("mode"),
                        "horizon_days": fe.get("horizon"),
                        "last_close": fe.get("last_close"),
                        "model_status": fe.get("model_status"),
                    }
                else:
                    foundation_warning = f"Kronos/Chronos-Bolt unavailable: {summarize_unavailable_reason()}"
            else:
                foundation_warning = f"Kronos/Chronos-Bolt unavailable: insufficient OHLCV rows ({len(rows)} < 32)"
        except Exception as exc:  # noqa: BLE001
            foundation_warning = f"Kronos/Chronos-Bolt unavailable: {exc}"
            precise_forecast = None
        if precise_forecast is None:
            precise_forecast = _build_precise_fallback(last_close, target_range, horizon_days, foundation_warning)
        try:
            from ...quant.models.price_point_calibrator import apply_latest_calibration, mark_uncalibrated  # type: ignore

            if precise_ohlcv_df is None and rows:
                import pandas as _pd

                precise_ohlcv_df = _pd.DataFrame([
                    {
                        "open": _safe_float(r.get("open"), r.get("close")),
                        "high": _safe_float(r.get("high"), r.get("close")),
                        "low": _safe_float(r.get("low"), r.get("close")),
                        "close": _safe_float(r.get("close")),
                        "volume": _safe_float(r.get("volume"), 0.0) or 0.0,
                    }
                    for r in rows
                ]).dropna(subset=["close"])
            if precise_forecast and precise_ohlcv_df is not None and len(precise_ohlcv_df):
                precise_forecast = apply_latest_calibration(
                    normalized["base"],
                    max(1, min(horizon_days, 14)),
                    precise_ohlcv_df,
                    precise_forecast,
                ) or precise_forecast
            else:
                precise_forecast = mark_uncalibrated(precise_forecast, foundation_warning)
        except Exception:
            if precise_forecast is not None:
                precise_forecast.setdefault("calibration_applied", False)
                precise_forecast.setdefault("calibration_warning", "Price calibration unavailable.")

        drivers = self._build_drivers(sentiment.get("scored_items") or [], signal, market)
        data_quality = {
            "market": bool(signal.get("ok")),
            "market_rows": len(rows),
            "sentiment": bool(sentiment.get("ok")),
            "sentiment_count": sentiment_count,
            "user_comments": bool(comment_items),
            "news": bool(news_items or article_items),
            "remote_news": bool(news_items),
            "selected_articles": bool(article_items),
            "selected_article_count": len(article_items),
            "derivatives": bool((market.get("derivatives") or {}).get("ok")),
            "status": status,
            "news_status": {k: v for k, v in news_status.items() if k != "items"},
        }
        rationale = self._build_rationale(normalized["base"], direction, composite, signal, sentiment_summary, market)

        return {
            "ok": True,
            "status": status,
            "symbol": normalized["base"],
            "pair": normalized["pair"],
            "horizon": "1w" if horizon_days == 7 else f"{horizon_days}d",
            "horizon_days": horizon_days,
            "direction": direction,
            "probability": probability,
            "confidence": _confidence_label(confidence_value),
            "confidence_score": round(confidence_value, 4),
            "score_breakdown": {
                "technical": round(tech_factor, 4),
                "sentiment": round(sentiment_factor, 4),
                "volume": round(volume_factor, 4),
                "derivatives": round(derivatives_factor, 4),
                "composite": round(composite, 4),
                "weights": {k: round(v, 4) for k, v in weights.items()},
            },
            "market": {
                "source": market.get("source"),
                "fetched_at": market.get("fetched_at"),
                "last_close": last_close,
                "ticker": market.get("ticker") or {},
                "signal": signal,
                "ohlcv_tail": rows[-60:],
                "derivatives": market.get("derivatives") or {},
            },
            "sentiment": {
                "summary": sentiment_summary,
                "model": sentiment.get("model"),
                "timeline": sentiment.get("timeline") or [],
            },
            "target_price_range": target_range,
            "precise_forecast": precise_forecast,
            "evidence": {
                "drivers": drivers,
                "comments": comment_items[:30],
                "articles": article_items[:20],
                "news": news_items[:10],
                "technical_votes": signal.get("votes") or [],
            },
            "data_quality": data_quality,
            "warnings": list(dict.fromkeys([w for w in warnings if w])),
            "rationale": rationale,
            "time_anchor": build_time_anchor() if horizon_days == 1 else None,
        }

    @staticmethod
    def _build_drivers(scored_items: List[Dict[str, Any]], signal: Dict[str, Any], market: Dict[str, Any]) -> List[Dict[str, Any]]:
        drivers: List[Dict[str, Any]] = []
        for vote in (signal.get("votes") or [])[:8]:
            drivers.append({
                "type": "technical",
                "title": vote.get("label"),
                "polarity": vote.get("polarity"),
                "score": vote.get("weight"),
            })
        ranked = sorted(
            scored_items,
            key=lambda item: abs(_safe_float((item.get("sentiment") or {}).get("compound"), 0.0) or 0.0) * _item_weight(item),
            reverse=True,
        )
        for item in ranked[:8]:
            sent = item.get("sentiment") or {}
            drivers.append({
                "type": "sentiment",
                "title": item.get("title") or item.get("text", "")[:100],
                "site": item.get("site"),
                "compound": sent.get("compound"),
                "label": sent.get("label"),
                "url": item.get("url") or "",
            })
        ticker = market.get("ticker") or {}
        if ticker.get("ok"):
            drivers.append({
                "type": "market",
                "title": "24h spot ticker",
                "price_change_pct_24h": ticker.get("price_change_pct_24h"),
                "quote_volume_24h": ticker.get("quote_volume_24h"),
            })
        return drivers[:14]

    @staticmethod
    def _build_rationale(
        symbol: str,
        direction: str,
        composite: float,
        signal: Dict[str, Any],
        sentiment_summary: Dict[str, Any],
        market: Dict[str, Any],
    ) -> str:
        tech = signal.get("direction") if signal.get("ok") else signal.get("reason", "no technical signal")
        sentiment_label = sentiment_summary.get("label", "neutral")
        count = sentiment_summary.get("count", 0)
        last = signal.get("last_close") or (market.get("ticker") or {}).get("last_price") or "n/a"
        return (
            f"{symbol} one-week direction is {direction} with composite score {composite:+.3f}. "
            f"Technical signal={tech}, sentiment={sentiment_label} (n={count}), last price={last}."
        )
