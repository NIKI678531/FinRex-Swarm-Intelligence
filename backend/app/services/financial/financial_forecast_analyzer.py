"""金融预测分析器（OIF + Forecast）。

聚合 market_provider / news_provider / sentiment_provider / time_pulse_model
（如有 simulation） / reaction fusion（如有），输出固定 schema 的金融预测结果。

输出结构（feed 给 FinancialOIFStrategy 注入到 prompt）：

{
    "target_asset": {symbol, type, market},
    "mode": "asset" | "event",
    "observed":  {price_facts, real_news, real_comments, ...},
    "inferred":  {sentiment_index, drivers, divergence_signals, ...},
    "simulated": {agent_scenarios, oasis_pulses, ...},
    "forecast":  {
        direction: "up|down|neutral",
        probability: float,
        horizon: "24h|72h|1w",
        confidence: "high|medium|low",
        target_price_range: {low, high} | None,
        risk_caveats: [...],
        rationale: str,
    },
    "data_quality": {market: bool, news: bool, sentiment: ok, simulation: bool},
}

走向判定：sentiment_score × technical_trend × oasis_pulse_intensity 三因子加权规则版。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .market_provider import MarketProvider
from .news_provider import NewsProvider
from .sentiment_provider import SentimentProvider

logger = logging.getLogger("finrex.financial.forecast_analyzer")


def _factor_from_sentiment(avg_compound: float) -> float:
    """情绪分数 → [-1, 1] 因子。"""
    return max(-1.0, min(1.0, avg_compound * 2.0))


def _factor_from_trend(indicators: Dict[str, Any]) -> float:
    """技术指标 → [-1, 1] 因子。"""
    if not indicators:
        return 0.0
    trend = indicators.get("trend")
    rsi = indicators.get("rsi14")
    return_5d = indicators.get("return_5d") or 0.0
    base = {"up": 0.6, "down": -0.6, "sideways": 0.0}.get(trend, 0.0)
    # RSI 极端区域反向修正
    if rsi is not None:
        if rsi > 75:
            base -= 0.2
        elif rsi < 25:
            base += 0.2
    base += max(-0.3, min(0.3, return_5d * 5.0))
    return max(-1.0, min(1.0, base))


def _factor_from_pulses(pulse_events: List[Dict[str, Any]]) -> float:
    """OASIS 脉冲强度 → [-1, 1] 因子（基于平均情绪偏移）。"""
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
    avg_shift = sum(shifts) / len(shifts)
    return max(-1.0, min(1.0, avg_shift * 1.5))


def _direction_label(score: float) -> str:
    if score > 0.15:
        return "up"
    if score < -0.15:
        return "down"
    return "neutral"


_ALLOWED_HORIZON_DAYS = (1, 3, 5, 10)


def _clamp_horizon_days(value, default: int = 1) -> int:
    """Normalize a forecast horizon to one of the supported day buckets."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    if n in _ALLOWED_HORIZON_DAYS:
        return n
    return min(_ALLOWED_HORIZON_DAYS, key=lambda d: abs(d - n))


def _confidence_label(data_quality: Dict[str, Any]) -> str:
    score = sum([
        2 if data_quality.get("market") else 0,
        1 if data_quality.get("news") else 0,
        1 if data_quality.get("sentiment") else 0,
        1 if data_quality.get("simulation") else 0,
    ])
    if score >= 4:
        return "high"
    if score >= 2:
        return "medium"
    return "low"


class FinancialForecastAnalyzer:
    """聚合输入 → OIF + Forecast 输出。"""

    def __init__(
        self,
        market_provider: Optional[MarketProvider] = None,
        news_provider: Optional[NewsProvider] = None,
        sentiment_provider: Optional[SentimentProvider] = None,
    ):
        self.market = market_provider or MarketProvider()
        self.news = news_provider or NewsProvider()
        self.sentiment = sentiment_provider or SentimentProvider()

    def analyze(
        self,
        target_asset: Optional[Dict[str, Any]],
        simulation_requirement: str,
        user_comments: Optional[List[Any]] = None,
        selected_articles: Optional[List[Any]] = None,
        oasis_dashboard: Optional[Dict[str, Any]] = None,
        reaction_fusion: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """主入口。"""
        target_asset = target_asset or {}
        symbol = (target_asset.get("symbol") or "").strip()
        asset_type = (target_asset.get("type") or "event").lower()
        horizon_days = _clamp_horizon_days(target_asset.get("horizon_days"))
        mode = "asset" if symbol and asset_type in {"stock", "crypto"} else "event"

        if mode == "asset" and asset_type == "crypto":
            try:
                return self._analyze_crypto_asset(
                    target_asset=target_asset,
                    symbol=symbol,
                    simulation_requirement=simulation_requirement,
                    user_comments=user_comments or [],
                    selected_articles=selected_articles or [],
                    oasis_dashboard=oasis_dashboard,
                    reaction_fusion=reaction_fusion,
                    horizon_days=horizon_days,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("CryptoForecastService failed for %s, fallback to generic analyzer: %s", symbol, exc)

        if mode == "asset" and asset_type == "stock":
            try:
                return self._analyze_stock_asset(
                    target_asset=target_asset,
                    symbol=symbol,
                    simulation_requirement=simulation_requirement,
                    user_comments=user_comments or [],
                    selected_articles=selected_articles or [],
                    oasis_dashboard=oasis_dashboard,
                    reaction_fusion=reaction_fusion,
                    horizon_days=horizon_days,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("StockForecastService failed for %s, fallback to generic analyzer: %s", symbol, exc)

        # 1) Market snapshot
        market_snapshot: Dict[str, Any] = {}
        if mode == "asset":
            market_snapshot = self.market.fetch_snapshot(symbol, asset_type=asset_type)

        # 2) News + user comments
        corpus = self.news.collect_corpus(
            symbol=symbol,
            asset_type=asset_type if mode == "asset" else "event",
            user_comments=user_comments or [],
            selected_articles=selected_articles or [],
        )

        # 3) Sentiment
        sentiment_result = self.sentiment.score_corpus(corpus["all"])

        # 4) OASIS pulses（如已有 dashboard 则消费）
        pulse_events: List[Dict[str, Any]] = []
        if isinstance(oasis_dashboard, dict):
            pulse_events = oasis_dashboard.get("pulse_events") or []

        # 5) 三因子加权得分
        f_sent = _factor_from_sentiment(sentiment_result["summary"]["avg_compound"])
        f_trend = _factor_from_trend(market_snapshot.get("indicators", {})) if mode == "asset" else 0.0
        f_pulse = _factor_from_pulses(pulse_events)

        # 权重：有标的时三者均衡；无标的时弱化技术面
        if mode == "asset":
            weights = {"sent": 0.4, "trend": 0.4, "pulse": 0.2}
        else:
            weights = {"sent": 0.6, "trend": 0.0, "pulse": 0.4}

        composite = (
            f_sent * weights["sent"]
            + f_trend * weights["trend"]
            + f_pulse * weights["pulse"]
        )
        direction = _direction_label(composite)
        probability = round(0.5 + composite / 2.0, 4)  # map [-1,1]->[0,1]

        # 6) 数据质量
        data_quality = {
            "market": bool(market_snapshot.get("ok")),
            "news": bool(corpus["news"] or corpus.get("articles")),
            "remote_news": bool(corpus["news"]),
            "selected_articles": bool(corpus.get("articles")),
            "selected_article_count": len(corpus.get("articles") or []),
            "sentiment": sentiment_result["ok"],
            "simulation": bool(pulse_events),
            "user_comments": bool(corpus["comments"]),
            "news_status": corpus.get("news_status") or {},
        }
        confidence = _confidence_label(data_quality)

        # 7) Risk caveats
        risk_caveats = self._build_risk_caveats(
            mode=mode,
            indicators=market_snapshot.get("indicators", {}),
            sentiment_summary=sentiment_result["summary"],
            data_quality=data_quality,
        )

        # 8) Target price range (asset mode only; ±1σ)
        target_range = None
        ind = market_snapshot.get("indicators") or {}
        if mode == "asset" and ind.get("last_close") and ind.get("volatility_30d"):
            last = float(ind["last_close"])
            vol = float(ind["volatility_30d"])
            # 1d horizon: next-day prediction
            band = last * vol * (1 ** 0.5)
            shift = composite * band
            target_range = {
                "low": round(last + shift - band, 4),
                "mid": round(last + shift, 4),
                "high": round(last + shift + band, 4),
                "horizon_days": 1,
            }

        # 8b) Precise foundation-model forecast (Kronos + Chronos). Optional, additive.
        precise_forecast = None
        foundation_warning = "Kronos/Chronos-Bolt unavailable; using deterministic range midpoint."
        try:
            ohlcv_recent = market_snapshot.get("ohlcv") or []
            if mode == "asset" and len(ohlcv_recent) >= 32:
                import pandas as _pd
                from ...quant.models.foundation_ensemble import predict_ensemble, summarize_unavailable_reason  # type: ignore
                ohlcv_df = _pd.DataFrame([
                    {
                        "open": r.get("open", r.get("close")),
                        "high": r.get("high", r.get("close")),
                        "low": r.get("low", r.get("close")),
                        "close": r.get("close"),
                        "volume": r.get("volume", 0.0),
                    }
                    for r in ohlcv_recent
                ]).dropna(subset=["close"])
                fe = predict_ensemble(ohlcv_df, horizon=1)
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
            elif mode == "asset":
                foundation_warning = f"Kronos/Chronos-Bolt unavailable: insufficient OHLCV rows ({len(ohlcv_recent)} < 32)"
        except Exception as exc:  # noqa: BLE001
            foundation_warning = f"Kronos/Chronos-Bolt unavailable: {exc}"
            precise_forecast = None
        if precise_forecast is None and mode == "asset":
            precise_forecast = self._build_precise_fallback(
                last_close=ind.get("last_close"),
                target_range=target_range,
                horizon_days=5,
                warning=f"{foundation_warning}; using deterministic range midpoint.",
            )

        rationale = self._build_rationale(
            mode=mode,
            symbol=symbol,
            sentiment_summary=sentiment_result["summary"],
            indicators=ind,
            pulse_count=len(pulse_events),
            composite=composite,
        )

        # 9) Reaction fusion 三层（若已存在直接复用）
        reaction_layers = self._extract_reaction_layers(reaction_fusion)

        return {
            "target_asset": {
                "symbol": symbol,
                "type": asset_type,
                "market": target_asset.get("market", ""),
            },
            "mode": mode,
            "observed": {
                "price_facts": market_snapshot.get("indicators", {}),
                "ohlcv_recent": market_snapshot.get("ohlcv", [])[-30:],
                "real_news": (corpus["news"] + corpus.get("articles", []))[:10],
                "selected_articles": (corpus.get("articles") or [])[:20],
                "real_comments": corpus["comments"][:20],
                "reaction_observed": reaction_layers.get("observed"),
            },
            "inferred": {
                "sentiment_index": sentiment_result["summary"],
                "sentiment_timeline": sentiment_result["timeline"][-50:],
                "sentiment_model": sentiment_result["model"],
                "drivers": self._extract_drivers(sentiment_result["scored_items"]),
                "divergence_signals": self._detect_divergence(ind, sentiment_result["summary"]),
                "reaction_inferred": reaction_layers.get("inferred"),
            },
            "simulated": {
                "oasis_pulses": pulse_events[:20],
                "agent_scenarios": (oasis_dashboard or {}).get("key_events", [])[:10],
                "reaction_simulated": reaction_layers.get("simulated"),
            },
            "forecast": {
                "direction": direction,
                "probability": probability,
                "horizon": "5d" if mode == "asset" else "72h",
                "confidence": confidence,
                "target_price_range": target_range,
                "precise_forecast": precise_forecast,
                "risk_caveats": risk_caveats,
                "rationale": rationale,
                "factors": {
                    "sentiment": round(f_sent, 4),
                    "technical_trend": round(f_trend, 4),
                    "oasis_pulse": round(f_pulse, 4),
                    "weights": weights,
                    "composite": round(composite, 4),
                },
            },
            "data_quality": data_quality,
            "simulation_requirement": simulation_requirement,
        }

    def _analyze_crypto_asset(
        self,
        target_asset: Dict[str, Any],
        symbol: str,
        simulation_requirement: str,
        user_comments: List[Any],
        selected_articles: List[Any],
        oasis_dashboard: Optional[Dict[str, Any]] = None,
        reaction_fusion: Optional[Dict[str, Any]] = None,
        horizon_days: int = 1,
    ) -> Dict[str, Any]:
        """Crypto-specific OIF context backed by real market data."""
        from .crypto_forecast_service import CryptoForecastService

        horizon_days = _clamp_horizon_days(horizon_days)
        crypto = CryptoForecastService(sentiment_provider=self.sentiment, news_provider=self.news).forecast(
            symbol=symbol or "BTC",
            horizon=horizon_days,
            comments=user_comments or [],
            articles=selected_articles or [],
        )
        reaction_layers = self._extract_reaction_layers(reaction_fusion)
        pulse_events: List[Dict[str, Any]] = []
        if isinstance(oasis_dashboard, dict):
            pulse_events = oasis_dashboard.get("pulse_events") or []

        market = crypto.get("market") or {}
        signal = market.get("signal") or {}
        ticker = market.get("ticker") or {}
        score_breakdown = crypto.get("score_breakdown") or {}
        price_facts: Dict[str, Any] = {
            "source": market.get("source"),
            "pair": crypto.get("pair"),
            "last_close": market.get("last_close"),
            "as_of": signal.get("as_of"),
            "technical_direction": signal.get("direction"),
            "technical_score": signal.get("score"),
            "expected_return_pct": signal.get("expected_return_pct"),
            "ticker_24h": ticker,
        }
        if isinstance(signal.get("indicators_last"), dict):
            price_facts.update(signal.get("indicators_last") or {})

        data_quality = dict(crypto.get("data_quality") or {})
        data_quality.update({
            "simulation": bool(pulse_events),
            "reaction_observed": bool(reaction_layers.get("observed")),
        })

        risk_caveats = self._build_crypto_risk_caveats(crypto)
        forecast = {
            "direction": crypto.get("direction", "neutral"),
            "probability": crypto.get("probability", 0.5),
            "horizon": crypto.get("horizon", "1w"),
            "confidence": crypto.get("confidence", "low"),
            "target_price_range": crypto.get("target_price_range"),
            "precise_forecast": crypto.get("precise_forecast"),
            "risk_caveats": risk_caveats,
            "rationale": crypto.get("rationale", ""),
            "status": crypto.get("status", "ok"),
            "factors": {
                "technical_trend": score_breakdown.get("technical", 0.0),
                "sentiment": score_breakdown.get("sentiment", 0.0),
                "volume": score_breakdown.get("volume", 0.0),
                "derivatives": score_breakdown.get("derivatives", 0.0),
                "composite": score_breakdown.get("composite", 0.0),
                "weights": score_breakdown.get("weights", {}),
            },
            "crypto_forecast": crypto,
        }

        evidence = crypto.get("evidence") or {}
        sentiment = crypto.get("sentiment") or {}
        return {
            "target_asset": {
                "symbol": crypto.get("symbol") or symbol,
                "type": "crypto",
                "market": target_asset.get("market") or crypto.get("pair") or "global",
            },
            "mode": "asset",
            "observed": {
                "price_facts": price_facts,
                "ohlcv_recent": (market.get("ohlcv_tail") or [])[-30:],
                "real_news": ((evidence.get("news") or []) + (evidence.get("articles") or []))[:10],
                "selected_articles": (evidence.get("articles") or [])[:20],
                "real_comments": (evidence.get("comments") or [])[:30],
                "reaction_observed": reaction_layers.get("observed"),
            },
            "inferred": {
                "sentiment_index": sentiment.get("summary") or {},
                "sentiment_timeline": (sentiment.get("timeline") or [])[-50:],
                "sentiment_model": sentiment.get("model"),
                "drivers": (evidence.get("drivers") or [])[:14],
                "technical_votes": evidence.get("technical_votes") or [],
                "crypto_score_breakdown": score_breakdown,
                "divergence_signals": self._detect_divergence(
                    {"trend": signal.get("direction")},
                    sentiment.get("summary") or {},
                ),
                "reaction_inferred": reaction_layers.get("inferred"),
            },
            "simulated": {
                "oasis_pulses": pulse_events[:20],
                "agent_scenarios": (oasis_dashboard or {}).get("key_events", [])[:10],
                "reaction_simulated": reaction_layers.get("simulated"),
            },
            "forecast": forecast,
            "data_quality": data_quality,
            "simulation_requirement": simulation_requirement,
        }

    def _analyze_stock_asset(
        self,
        target_asset: Dict[str, Any],
        symbol: str,
        simulation_requirement: str,
        user_comments: List[Any],
        selected_articles: List[Any],
        oasis_dashboard: Optional[Dict[str, Any]] = None,
        reaction_fusion: Optional[Dict[str, Any]] = None,
        horizon_days: int = 1,
    ) -> Dict[str, Any]:
        """Stock-specific OIF context backed by StockForecastService."""
        from .stock_forecast_service import StockForecastService

        horizon_days = _clamp_horizon_days(horizon_days)
        stock = StockForecastService(
            market_provider=self.market,
            sentiment_provider=self.sentiment,
            news_provider=self.news,
        ).forecast(
            symbol=symbol,
            comments=user_comments or [],
            articles=selected_articles or [],
            oasis_dashboard=oasis_dashboard,
            horizon_days=horizon_days,
        )
        reaction_layers = self._extract_reaction_layers(reaction_fusion)
        pulse_events: List[Dict[str, Any]] = []
        if isinstance(oasis_dashboard, dict):
            pulse_events = oasis_dashboard.get("pulse_events") or []

        market = stock.get("market") or {}
        indicators = market.get("indicators") or {}
        sentiment = stock.get("sentiment") or {}
        evidence = stock.get("evidence") or {}
        breakdown = stock.get("score_breakdown") or {}
        data_quality = dict(stock.get("data_quality") or {})
        data_quality["simulation"] = bool(pulse_events)

        risk_caveats = self._build_stock_risk_caveats(stock)

        forecast = {
            "direction": stock.get("direction", "neutral"),
            "probability": stock.get("probability", 0.5),
            "horizon": stock.get("horizon", "1d"),
            "confidence": stock.get("confidence", "low"),
            "target_price_range": stock.get("target_price_range"),
            "precise_forecast": stock.get("precise_forecast"),
            "risk_caveats": risk_caveats,
            "rationale": stock.get("rationale", ""),
            "status": stock.get("status", "ok"),
            "factors": {
                "sentiment": breakdown.get("sentiment", 0.0),
                "technical_trend": breakdown.get("technical", 0.0),
                "market_beta": breakdown.get("market_beta", 0.0),
                "overnight_gap": breakdown.get("overnight_gap", 0.0),
                "options_iv": breakdown.get("options_iv", 0.0),
                "oasis_pulse": breakdown.get("oasis_pulse", 0.0),
                "composite": breakdown.get("composite", 0.0),
                "weights": breakdown.get("weights", {}),
            },
            "stock_forecast": stock,
        }

        price_facts: Dict[str, Any] = {
            "source": market.get("source"),
            "last_close": market.get("last_close"),
            "as_of": market.get("fetched_at"),
            **indicators,
        }
        overnight = market.get("overnight_gap") or {}
        bench = market.get("benchmark_trend") or {}
        if overnight.get("ok"):
            price_facts["overnight_gap_pct"] = overnight.get("gap_pct")
        if bench.get("ok"):
            price_facts["benchmark"] = bench.get("benchmark")
            price_facts["benchmark_return_30d"] = bench.get("benchmark_return_30d")

        return {
            "target_asset": {
                "symbol": stock.get("symbol") or symbol,
                "type": "stock",
                "market": target_asset.get("market", ""),
            },
            "mode": "asset",
            "observed": {
                "price_facts": price_facts,
                "ohlcv_recent": (market.get("ohlcv_tail") or [])[-30:],
                "real_news": ((evidence.get("news") or []) + (evidence.get("articles") or []))[:10],
                "selected_articles": (evidence.get("articles") or [])[:20],
                "real_comments": (evidence.get("comments") or [])[:30],
                "reaction_observed": reaction_layers.get("observed"),
            },
            "inferred": {
                "sentiment_index": sentiment.get("summary") or {},
                "sentiment_timeline": (sentiment.get("timeline") or [])[-50:],
                "sentiment_model": sentiment.get("model"),
                "drivers": (evidence.get("drivers") or [])[:14],
                "stock_score_breakdown": breakdown,
                "divergence_signals": self._detect_divergence(
                    {"trend": indicators.get("trend")},
                    sentiment.get("summary") or {},
                ),
                "reaction_inferred": reaction_layers.get("inferred"),
            },
            "simulated": {
                "oasis_pulses": pulse_events[:20],
                "agent_scenarios": (oasis_dashboard or {}).get("key_events", [])[:10],
                "reaction_simulated": reaction_layers.get("simulated"),
            },
            "forecast": forecast,
            "data_quality": data_quality,
            "simulation_requirement": simulation_requirement,
        }

    @staticmethod
    def _build_stock_risk_caveats(stock: Dict[str, Any]) -> List[str]:
        caveats: List[str] = []
        dq = stock.get("data_quality") or {}
        if dq.get("earnings_in_window"):
            window = (stock.get("market") or {}).get("earnings_window") or {}
            d = window.get("days_to_event")
            caveats.append(
                f"Earnings event within {abs(d) if d is not None else '<5'} day(s) — predictions downgraded."
            )
        if not dq.get("market"):
            caveats.append("Daily OHLCV unavailable — technical factor dropped.")
        if not dq.get("overnight_gap"):
            caveats.append("Overnight gap data unavailable — factor dropped.")
        if not dq.get("benchmark_trend"):
            caveats.append("Sector benchmark trend unavailable — factor dropped.")
        if not dq.get("options_signal"):
            caveats.append("Options PCR unavailable on current FMP tier — factor dropped.")
        if int(dq.get("sentiment_count") or 0) < 5:
            caveats.append("Sentiment sample <5 — confidence reduced.")
        for w in stock.get("warnings") or []:
            caveats.append(str(w))
        return list(dict.fromkeys([c for c in caveats if c]))

    # ── helpers ──

    @staticmethod
    def _build_precise_fallback(
        last_close: Any,
        target_range: Optional[Dict[str, Any]],
        horizon_days: int,
        warning: str,
    ) -> Optional[Dict[str, Any]]:
        try:
            last = float(last_close) if last_close not in (None, "") else None
        except (TypeError, ValueError):
            last = None
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

    @staticmethod
    def _build_risk_caveats(
        mode: str,
        indicators: Dict[str, Any],
        sentiment_summary: Dict[str, Any],
        data_quality: Dict[str, Any],
    ) -> List[str]:
        caveats: List[str] = []
        if not data_quality.get("market") and mode == "asset":
            caveats.append("行情数据缺失，技术面分析降级为空")
        if not data_quality.get("remote_news") and data_quality.get("selected_articles"):
            caveats.append("实时 FMP 新闻拉取失败或未配置，但已使用 Step1 已选 FMP/市场新闻种子")
        elif not data_quality.get("news"):
            caveats.append("实时新闻拉取失败或未配置 FMP_API_KEY，舆情样本量受限")
        if not data_quality.get("simulation"):
            caveats.append("无 OASIS 脉冲信号，模拟层仅基于已有评论与行情")
        if sentiment_summary.get("count", 0) < 5:
            caveats.append("情绪样本不足（<5 条），结论置信度较低")
        rsi = indicators.get("rsi14")
        if rsi is not None:
            if rsi > 75:
                caveats.append(f"RSI={rsi:.1f}，处于超买区，存在均值回归风险")
            elif rsi < 25:
                caveats.append(f"RSI={rsi:.1f}，处于超卖区，可能存在技术反弹")
        return caveats

    @staticmethod
    def _build_crypto_risk_caveats(crypto: Dict[str, Any]) -> List[str]:
        caveats = [
            "虚拟资产价格波动高，预测仅代表研究信号，不构成投资建议",
        ]
        data_quality = crypto.get("data_quality") or {}
        if not data_quality.get("market"):
            caveats.append("Binance/yfinance 行情不足，技术面预测不可用")
        if not data_quality.get("sentiment"):
            caveats.append("真实舆情样本不足，舆情因子降权")
        elif int(data_quality.get("sentiment_count") or 0) < 5:
            caveats.append("真实评论/新闻样本少于 5 条，舆情置信度较低")
        if not data_quality.get("derivatives"):
            caveats.append("衍生品资金费率或持仓数据不可用，资金面因子降权")
        for warning in crypto.get("warnings") or []:
            caveats.append(str(warning))
        return list(dict.fromkeys([c for c in caveats if c]))

    @staticmethod
    def _build_rationale(
        mode: str,
        symbol: str,
        sentiment_summary: Dict[str, Any],
        indicators: Dict[str, Any],
        pulse_count: int,
        composite: float,
    ) -> str:
        target_label = symbol if mode == "asset" else "事件级市场反应"
        s_label = sentiment_summary.get("label", "neutral")
        avg = sentiment_summary.get("avg_compound", 0.0)
        trend = indicators.get("trend", "n/a") if mode == "asset" else "n/a"
        return (
            f"{target_label} 综合得分 {composite:+.3f}：情绪面 {s_label} "
            f"(avg={avg:+.3f}, n={sentiment_summary.get('count', 0)})，"
            f"技术面趋势 {trend}，OASIS 脉冲事件 {pulse_count} 条。"
        )

    @staticmethod
    def _extract_drivers(scored_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """从评分项中抽取最强 ±3 条作为驱动因素。"""
        if not scored_items:
            return []
        sorted_items = sorted(
            scored_items,
            key=lambda x: abs(x["sentiment"]["compound"]),
            reverse=True,
        )
        drivers: List[Dict[str, Any]] = []
        for it in sorted_items[:6]:
            drivers.append({
                "title": it.get("title", "")[:120],
                "site": it.get("site", ""),
                "compound": it["sentiment"]["compound"],
                "label": it["sentiment"].get("label"),
                "url": it.get("url", ""),
            })
        return drivers

    @staticmethod
    def _detect_divergence(
        indicators: Dict[str, Any],
        sentiment_summary: Dict[str, Any],
    ) -> List[str]:
        signals: List[str] = []
        trend = indicators.get("trend")
        s_label = sentiment_summary.get("label", "neutral")
        if trend == "up" and s_label == "bearish":
            signals.append("价格上行但情绪转空：potential top divergence")
        if trend == "down" and s_label == "bullish":
            signals.append("价格下行但情绪转多：potential bottom divergence")
        return signals

    @staticmethod
    def _extract_reaction_layers(fusion: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(fusion, dict):
            return {}
        return {
            "observed": fusion.get("observed"),
            "inferred": fusion.get("inferred"),
            "simulated": fusion.get("simulated"),
        }
