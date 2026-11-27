"""股票方向预测服务（Phase D）。

镜像 ``CryptoForecastService`` 结构，但因子配置面向美股：

- sentiment      : weight=0.25
- technical      : weight=0.15
- market_beta    : weight=0.20  （SOXX / QQQ / SPY 基准动量 × beta 符号）
- overnight_gap  : weight=0.20  （上一开盘 vs 前一收盘）
- options_iv     : weight=0.10  （FMP PCR；不可用时 drop+摊分）
- oasis_pulse    : weight=0.10  （OASIS 脉冲事件平均情绪偏移）

合成分阈值 ``±0.08``；财报窗口 ≤5 个交易日强制 ``confidence=low``。
所有数据源失败均不抛异常，降级为 reason + 权重重分配。
"""

from __future__ import annotations

import logging
import math
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .market_provider import MarketProvider
from .news_provider import NewsProvider
from .sentiment_provider import SentimentProvider

logger = logging.getLogger("finrex.financial.stock_forecast_service")

# Target weights when every factor is available. When a factor is missing
# (e.g. options PCR), its weight is redistributed proportionally to the rest.
_STOCK_WEIGHTS: Dict[str, float] = {
    "sentiment": 0.25,
    "technical": 0.15,
    "market_beta": 0.20,
    "overnight_gap": 0.20,
    "options_iv": 0.10,
    "oasis_pulse": 0.10,
}
_DIRECTION_THRESHOLD = 0.08
_EARNINGS_CAVEAT_DAYS = 5


def _clamp(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _factor_from_trend(indicators: Dict[str, Any]) -> float:
    if not indicators:
        return 0.0
    trend = indicators.get("trend")
    rsi = indicators.get("rsi14")
    return_5d = indicators.get("return_5d") or 0.0
    base = {"up": 0.6, "down": -0.6, "sideways": 0.0}.get(trend, 0.0)
    if rsi is not None:
        if rsi > 75:
            base -= 0.2
        elif rsi < 25:
            base += 0.2
    base += max(-0.3, min(0.3, return_5d * 5.0))
    return _clamp(base)


def _factor_from_sentiment(summary: Dict[str, Any]) -> float:
    weighted = _safe_float(summary.get("weighted_avg_compound"))
    if weighted is None:
        weighted = _safe_float(summary.get("avg_compound"), 0.0) or 0.0
    return _clamp(weighted * 1.6)


def _factor_from_pulses(pulse_events: List[Dict[str, Any]]) -> float:
    if not pulse_events:
        return 0.0
    shifts: List[float] = []
    for ev in pulse_events:
        shift = ev.get("sentiment_shift") or ev.get("avg_sentiment") or 0.0
        try:
            shifts.append(float(shift))
        except (TypeError, ValueError):
            continue
    if not shifts:
        return 0.0
    return _clamp((sum(shifts) / len(shifts)) * 1.5)


def _weighted_sentiment_summary(sentiment_result: Dict[str, Any]) -> Dict[str, Any]:
    """Attach ``weighted_avg_compound`` (engagement + recency) to summary."""
    scored = sentiment_result.get("scored_items") or []
    summary = dict(sentiment_result.get("summary") or {})
    if not scored:
        summary.setdefault("weighted_avg_compound", 0.0)
        summary.setdefault("weighted_count", 0.0)
        return summary
    weighted_sum = 0.0
    weight_total = 0.0
    now = datetime.utcnow()
    for item in scored:
        compound = _safe_float((item.get("sentiment") or {}).get("compound"), 0.0) or 0.0
        weight = float(item.get("weight") or 1.0)
        likes = _safe_float(item.get("like_count"), 0.0) or 0.0
        replies = _safe_float(item.get("reply_count"), 0.0) or 0.0
        weight += min(2.0, math.log1p(max(0.0, likes)) / 4.0)
        weight += min(1.0, math.log1p(max(0.0, replies)) / 5.0)
        ts = item.get("published_at")
        if ts:
            try:
                dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00")).replace(tzinfo=None)
                age_h = max(0.0, (now - dt).total_seconds() / 3600.0)
                if age_h <= 24:
                    weight += 0.5
                elif age_h <= 72:
                    weight += 0.25
            except Exception:  # noqa: BLE001
                pass
        weighted_sum += compound * weight
        weight_total += weight
    summary["weighted_avg_compound"] = round(weighted_sum / weight_total if weight_total else 0.0, 4)
    summary["weighted_count"] = round(weight_total, 3)
    return summary


def _normalize_weights(available: Dict[str, float]) -> Dict[str, float]:
    total = sum(v for v in available.values() if v > 0)
    if total <= 0:
        return {k: 0.0 for k in available}
    return {k: (v / total if v > 0 else 0.0) for k, v in available.items()}


def _confidence(value: float) -> str:
    if value >= 0.65:
        return "high"
    if value >= 0.40:
        return "medium"
    return "low"


def _format_foundation_forecast(fe: Dict[str, Any]) -> Dict[str, Any]:
    return {
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


def _build_precise_fallback(
    last_close: Any,
    target_range: Optional[Dict[str, Any]],
    horizon_days: int,
    warning: str,
) -> Optional[Dict[str, Any]]:
    last = _safe_float(last_close)
    if isinstance(target_range, dict):
        try:
            low = float(target_range.get("low"))
            high = float(target_range.get("high"))
            mid = float(target_range.get("mid", (low + high) / 2.0))
            return {
                "predicted_price": round(mid, 4),
                "p10": round(low, 4),
                "p50": round(mid, 4),
                "p90": round(high, 4),
                "p_up": None if not last else round(1.0 if mid > last else 0.0, 4),
                "expected_return": None if not last else round(mid / last - 1.0, 6),
                "uncertainty": None,
                "cross_model_agreement": None,
                "mode": "technical_range_fallback",
                "horizon_days": horizon_days,
                "last_close": last,
                "source": "target_price_range_midpoint",
                "warning": warning,
            }
        except (TypeError, ValueError):
            pass
    if last:
        band = last * 0.02
        return {
            "predicted_price": round(last, 4),
            "p10": round(last - band, 4),
            "p50": round(last, 4),
            "p90": round(last + band, 4),
            "p_up": 0.5,
            "expected_return": 0.0,
            "uncertainty": None,
            "cross_model_agreement": None,
            "mode": "last_close_fallback",
            "horizon_days": horizon_days,
            "last_close": last,
            "source": "last_close_plus_minus_2pct",
            "warning": warning,
        }
    return None


def build_precise_forecast_from_ohlcv(
    rows: List[Dict[str, Any]],
    last_close: Any,
    target_range: Optional[Dict[str, Any]],
    horizon_days: int = 1,
) -> Optional[Dict[str, Any]]:
    """Build Kronos/Chronos-Bolt stock price forecast with a range fallback."""
    clean_horizon = max(1, min(int(horizon_days or 1), 14))
    foundation_warning = "Kronos/Chronos-Bolt unavailable; using deterministic range midpoint."
    ohlcv_rows = rows or []
    if last_close in (None, "") and ohlcv_rows:
        last_close = ohlcv_rows[-1].get("close")

    try:
        if len(ohlcv_rows) >= 32:
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
                for r in ohlcv_rows
            ]).dropna(subset=["close"])
            if len(ohlcv_df) >= 32:
                fe = predict_ensemble(ohlcv_df, horizon=clean_horizon)
                if fe:
                    return _format_foundation_forecast(fe)
                foundation_warning = f"Kronos/Chronos-Bolt unavailable: {summarize_unavailable_reason()}"
            else:
                foundation_warning = (
                    f"Kronos/Chronos-Bolt unavailable: insufficient OHLCV rows "
                    f"({len(ohlcv_df)} < 32)"
                )
        else:
            foundation_warning = (
                f"Kronos/Chronos-Bolt unavailable: insufficient OHLCV rows "
                f"({len(ohlcv_rows)} < 32)"
            )
    except Exception as exc:  # noqa: BLE001
        foundation_warning = f"Kronos/Chronos-Bolt unavailable: {exc}"

    return _build_precise_fallback(last_close, target_range, clean_horizon, foundation_warning)


class StockForecastService:
    """Generate a structured stock directional forecast (1-5d horizon)."""

    def __init__(
        self,
        market_provider: Optional[MarketProvider] = None,
        sentiment_provider: Optional[SentimentProvider] = None,
        news_provider: Optional[NewsProvider] = None,
    ):
        self.market = market_provider or MarketProvider()
        self.sentiment = sentiment_provider or SentimentProvider()
        self.news = news_provider or NewsProvider()

    def forecast(
        self,
        symbol: str,
        comments: Optional[List[Any]] = None,
        articles: Optional[List[Any]] = None,
        oasis_dashboard: Optional[Dict[str, Any]] = None,
        horizon_days: int = 1,
    ) -> Dict[str, Any]:
        sym = (symbol or "").strip().upper()
        warnings: List[str] = []
        if not sym:
            return self._empty(reason="no symbol")

        # 1) Market snapshot (180d OHLCV + indicators)
        snapshot = self.market.fetch_snapshot(sym, asset_type="stock", lookback_days=180)
        indicators = snapshot.get("indicators") or {}
        last_close = _safe_float(indicators.get("last_close"))

        # 2) Stock corpus: FMP stock_news 72h + press releases + general news + selected/comments
        corpus = self.news.collect_corpus(
            symbol=sym,
            asset_type="stock",
            user_comments=comments or [],
            selected_articles=articles or [],
            news_limit=20,
            hours=72,
            include_press_releases=True,
            include_general_news=True,
            general_news_query=sym,
        )
        sentiment_result = self.sentiment.score_corpus(corpus["all"])
        sentiment_summary = _weighted_sentiment_summary(sentiment_result)

        # 3) Stock-specific market factors
        gap = self.market.fetch_overnight_gap(sym)
        beta = self.market.fetch_benchmark_trend(sym, lookback_days=30)
        options = self.market.fetch_options_signal(sym)
        earnings = self.market.fetch_earnings_window(sym, window_days=_EARNINGS_CAVEAT_DAYS)

        # 4) OASIS pulses (optional)
        pulse_events: List[Dict[str, Any]] = []
        if isinstance(oasis_dashboard, dict):
            pulse_events = oasis_dashboard.get("pulse_events") or []

        # 5) Compute per-factor scores
        f_sent = _factor_from_sentiment(sentiment_summary)
        f_tech = _factor_from_trend(indicators) if snapshot.get("ok") else 0.0
        f_beta = float(beta.get("factor") or 0.0) if beta.get("ok") else 0.0
        f_gap = float(gap.get("factor") or 0.0) if gap.get("ok") else 0.0
        f_opt = float(options.get("factor") or 0.0) if options.get("ok") else 0.0
        f_pulse = _factor_from_pulses(pulse_events)

        factors = {
            "sentiment": round(f_sent, 4),
            "technical": round(f_tech, 4),
            "market_beta": round(f_beta, 4),
            "overnight_gap": round(f_gap, 4),
            "options_iv": round(f_opt, 4),
            "oasis_pulse": round(f_pulse, 4),
        }

        # 6) Weight availability mask → redistribute
        sentiment_count = int(sentiment_summary.get("count") or 0)
        available: Dict[str, float] = {
            "sentiment": _STOCK_WEIGHTS["sentiment"] if (sentiment_result.get("ok") and sentiment_count >= 1) else 0.0,
            "technical": _STOCK_WEIGHTS["technical"] if snapshot.get("ok") else 0.0,
            "market_beta": _STOCK_WEIGHTS["market_beta"] if beta.get("ok") else 0.0,
            "overnight_gap": _STOCK_WEIGHTS["overnight_gap"] if gap.get("ok") else 0.0,
            "options_iv": _STOCK_WEIGHTS["options_iv"] if options.get("ok") else 0.0,
            "oasis_pulse": _STOCK_WEIGHTS["oasis_pulse"] if pulse_events else 0.0,
        }
        weights = _normalize_weights(available)
        composite = sum(factors[k] * weights[k] for k in factors)

        # 7) Direction + confidence
        if abs(composite) < _DIRECTION_THRESHOLD:
            direction = "neutral"
        else:
            direction = "up" if composite > 0 else "down"

        # Foundation confidence proxy: |composite| + coverage + agreement bonus
        coverage = sum(1 for v in available.values() if v > 0) / float(len(available))
        agreement_pairs = [
            (f_sent, f_tech),
            (f_sent, f_beta),
            (f_gap, f_beta),
            (f_sent, f_gap),
        ]
        agreement_bonus = 0.0
        for a, b in agreement_pairs:
            if a == 0 or b == 0:
                continue
            if (a > 0 and b > 0) or (a < 0 and b < 0):
                agreement_bonus += 0.05
        confidence_value = min(0.95, abs(composite) * 0.6 + coverage * 0.35 + agreement_bonus)
        if sentiment_count < 5:
            confidence_value *= 0.8
            warnings.append("Sentiment sample <5 — low confidence baseline.")
        if earnings.get("ok") and earnings.get("in_window"):
            confidence_value = min(confidence_value, 0.35)
            warnings.append(
                f"Earnings event within {abs(earnings.get('days_to_event') or 0)} day(s) "
                f"({earnings.get('event_date')}) — direction call downgraded to low confidence."
            )
        confidence = _confidence(confidence_value)
        if earnings.get("ok") and earnings.get("in_window"):
            confidence = "low"

        probability = round(max(0.15, min(0.85, 0.5 + composite * 0.45)), 4)

        # 8) Target range (use volatility_30d * sqrt(horizon))
        target_range: Optional[Dict[str, Any]] = None
        vol_30d = _safe_float(indicators.get("volatility_30d"))
        if last_close and vol_30d:
            band = last_close * vol_30d * math.sqrt(max(horizon_days, 1))
            shift = composite * band
            target_range = {
                "low": round(last_close + shift - band, 4),
                "mid": round(last_close + shift, 4),
                "high": round(last_close + shift + band, 4),
                "horizon_days": horizon_days,
            }

        precise_forecast = build_precise_forecast_from_ohlcv(
            rows=snapshot.get("ohlcv") or [],
            last_close=last_close,
            target_range=target_range,
            horizon_days=horizon_days,
        )

        # 9) Data quality + warnings
        if not gap.get("ok"):
            warnings.append(f"Overnight gap unavailable: {gap.get('reason') or 'n/a'}")
        if not beta.get("ok"):
            warnings.append(f"Benchmark trend unavailable: {beta.get('reason') or 'n/a'}")
        if not options.get("ok"):
            warnings.append(f"Options PCR unavailable: {options.get('reason') or 'n/a'}")
        if not snapshot.get("ok"):
            warnings.append("Daily OHLCV unavailable — technical factor dropped.")

        data_quality = {
            "market": bool(snapshot.get("ok")),
            "market_rows": snapshot.get("rows_count") or 0,
            "sentiment": bool(sentiment_result.get("ok")),
            "sentiment_count": sentiment_count,
            "news": bool(corpus.get("news") or corpus.get("articles")),
            "remote_news": bool(corpus.get("news")),
            "selected_articles": bool(corpus.get("articles")),
            "selected_article_count": len(corpus.get("articles") or []),
            "user_comments": bool(corpus.get("comments")),
            "press_releases": bool(corpus.get("press_status", {}).get("ok")),
            "general_news": bool(corpus.get("general_status", {}).get("ok")),
            "overnight_gap": bool(gap.get("ok")),
            "benchmark_trend": bool(beta.get("ok")),
            "options_signal": bool(options.get("ok")),
            "earnings_window": bool(earnings.get("ok")),
            "earnings_in_window": bool(earnings.get("in_window")),
            "simulation": bool(pulse_events),
        }

        rationale = self._build_rationale(sym, direction, composite, factors, sentiment_summary, gap, beta, earnings)
        drivers = self._build_drivers(sentiment_result.get("scored_items") or [], factors, beta, gap)

        return {
            "ok": True,
            "status": "ok",
            "symbol": sym,
            "asset_type": "stock",
            "horizon_days": horizon_days,
            "horizon": f"{horizon_days}d",
            "direction": direction,
            "probability": probability,
            "confidence": confidence,
            "confidence_score": round(confidence_value, 4),
            "score_breakdown": {
                **factors,
                "composite": round(composite, 4),
                "weights": {k: round(v, 4) for k, v in weights.items()},
                "target_weights": _STOCK_WEIGHTS,
                "threshold": _DIRECTION_THRESHOLD,
            },
            "market": {
                "source": snapshot.get("source"),
                "fetched_at": snapshot.get("fetched_at"),
                "last_close": last_close,
                "indicators": indicators,
                "ohlcv_tail": (snapshot.get("ohlcv") or [])[-90:],
                "overnight_gap": gap,
                "benchmark_trend": beta,
                "options_signal": options,
                "earnings_window": earnings,
            },
            "sentiment": {
                "summary": sentiment_summary,
                "model": sentiment_result.get("model"),
                "timeline": (sentiment_result.get("timeline") or [])[-50:],
            },
            "target_price_range": target_range,
            "evidence": {
                "drivers": drivers,
                "news": (corpus.get("news") or [])[:10],
                "articles": (corpus.get("articles") or [])[:20],
                "comments": (corpus.get("comments") or [])[:30],
            },
            "data_quality": data_quality,
            "precise_forecast": precise_forecast,
            "warnings": list(dict.fromkeys([w for w in warnings if w])),
            "rationale": rationale,
        }

    @staticmethod
    def _empty(reason: str) -> Dict[str, Any]:
        return {
            "ok": False,
            "status": "insufficient_data",
            "direction": "neutral",
            "probability": 0.5,
            "confidence": "low",
            "warnings": [reason],
            "score_breakdown": {"composite": 0.0, "weights": {}, "target_weights": _STOCK_WEIGHTS},
            "data_quality": {},
        }

    @staticmethod
    def _build_rationale(
        symbol: str,
        direction: str,
        composite: float,
        factors: Dict[str, float],
        sentiment_summary: Dict[str, Any],
        gap: Dict[str, Any],
        beta: Dict[str, Any],
        earnings: Dict[str, Any],
    ) -> str:
        s_label = sentiment_summary.get("label", "neutral")
        s_n = sentiment_summary.get("count", 0)
        gap_str = f"{(gap.get('gap_pct') or 0) * 100:+.2f}%" if gap.get("ok") else "n/a"
        bench = beta.get("benchmark") if beta.get("ok") else "n/a"
        bench_ret = f"{(beta.get('benchmark_return_30d') or 0) * 100:+.2f}%" if beta.get("ok") else "n/a"
        earn_str = ""
        if earnings.get("ok"):
            d = earnings.get("days_to_event")
            if d is not None:
                earn_str = f" Earnings T{d:+d}d ({earnings.get('event_date')})."
        return (
            f"{symbol} composite {composite:+.3f} → {direction}. "
            f"Sentiment={s_label} (n={s_n}, factor={factors['sentiment']:+.2f}), "
            f"technical={factors['technical']:+.2f}, "
            f"overnight gap={gap_str} (factor={factors['overnight_gap']:+.2f}), "
            f"{bench} 30d={bench_ret} (factor={factors['market_beta']:+.2f}).{earn_str}"
        )

    @staticmethod
    def _build_drivers(
        scored_items: List[Dict[str, Any]],
        factors: Dict[str, float],
        beta: Dict[str, Any],
        gap: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        drivers: List[Dict[str, Any]] = []
        if gap.get("ok"):
            drivers.append({
                "type": "technical",
                "title": f"Overnight gap {(gap.get('gap_pct') or 0) * 100:+.2f}%",
                "polarity": "up" if (gap.get("gap_pct") or 0) > 0 else "down",
                "score": factors.get("overnight_gap"),
            })
        if beta.get("ok"):
            drivers.append({
                "type": "macro",
                "title": f"{beta.get('benchmark')} 30d {(beta.get('benchmark_return_30d') or 0) * 100:+.2f}%",
                "polarity": "up" if (beta.get("benchmark_return_30d") or 0) > 0 else "down",
                "score": factors.get("market_beta"),
            })
        ranked = sorted(
            scored_items,
            key=lambda it: abs(float((it.get("sentiment") or {}).get("compound") or 0.0)) * float(it.get("weight") or 1.0),
            reverse=True,
        )
        for it in ranked[:8]:
            sent = it.get("sentiment") or {}
            drivers.append({
                "type": "sentiment",
                "title": (it.get("title") or it.get("text", "") or "")[:120],
                "site": it.get("site") or it.get("source"),
                "compound": sent.get("compound"),
                "label": sent.get("label"),
                "url": it.get("url") or "",
                "source": it.get("sentiment_source") or it.get("source"),
            })
        return drivers[:14]
