"""Forecast & allocation orchestration service.

Sits *next to* ``ReportStrategyService`` rather than inside it. The flow:

    1. Pull existing strategy bundle (themes already extracted from the report)
    2. Derive a CSOP ETF candidate pool from the universe by theme
    3. For each candidate, fetch 6-month OHLCV via ``MarketDataService``
       and compute indicator votes via ``signal_engine``
    4. Combine theme score + technical score - risk penalty into a unified
       ``combined_score``; rank, cap by risk tier, normalise to 100% weights
    5. Persist the bundle to ``uploads/asset_allocation/<report_id>.json``
       so subsequent calls are instant unless ``force=True``

The output schema is consumed by:
    GET /api/report/<id>/asset-allocation
    GET /api/asset-allocation/etf/<code>/forecast
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from ...config import Config
from ..report_strategy import ReportStrategyService
from .etf_universe import EtfUniverse
from .market_data import MarketDataService
from .risk_metrics import tier_cap, tier_penalty
from .signal_engine import compute_signals, backtest_hit_rate

logger = logging.getLogger("finrex.asset_forecast.service")

STORAGE_DIR = os.path.join(Config.UPLOAD_FOLDER, "asset_allocation")

# Score weights for the combined ranking
W_THEME = 0.40
W_TECH = 0.40
W_RISK = 0.20

# Map technical direction → signed unit score
_DIR_SCORE = {"bullish": 1.0, "neutral": 0.0, "bearish": -1.0}


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _ensure_dir() -> None:
    os.makedirs(STORAGE_DIR, exist_ok=True)


def _bundle_path(report_id: str) -> str:
    return os.path.join(STORAGE_DIR, f"{report_id}.json")


# ---------------------------------------------------------------------------


class AssetForecastService:
    """Build & cache a CSOP ETF asset-allocation bundle for a given report."""

    # ---- persistence -------------------------------------------------

    @classmethod
    def get_bundle(cls, report_id: str) -> Optional[Dict[str, Any]]:
        path = _bundle_path(report_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("read asset-allocation cache failed for %s: %s", report_id, exc)
            return None

    @classmethod
    def save_bundle(cls, report_id: str, bundle: Dict[str, Any]) -> None:
        _ensure_dir()
        with open(_bundle_path(report_id), "w", encoding="utf-8") as f:
            json.dump(bundle, f, ensure_ascii=False, indent=2)

    # ---- main entry --------------------------------------------------

    @classmethod
    def build_for_report(
        cls,
        report: Dict[str, Any],
        force: bool = False,
        top_n: int = 8,
        horizon_days: int = 1,
        with_backtest: bool = True,
    ) -> Dict[str, Any]:
        if hasattr(report, "to_dict"):
            report = report.to_dict()
        report_id = report.get("report_id")
        if not report_id:
            raise ValueError("report_id is required")

        if not force:
            cached = cls.get_bundle(report_id)
            if cached:
                return cached

        # 1) Pull/build strategy signals from the existing pipeline.
        strategy = ReportStrategyService.get_report_strategy(report_id)
        if not strategy:
            strategy = ReportStrategyService.build_strategy_for_report(report)

        signals = strategy.get("signals") or []
        theme_keys: List[str] = []
        theme_score_by_key: Dict[str, float] = {}
        for sig in signals:
            key = sig.get("theme_key") or "report_core"
            if key in ("report_core", "", None):
                continue
            theme_keys.append(key)
            # Use confidence as a proxy theme strength; default 0.6
            try:
                strength = float(sig.get("confidence") or 0.6)
            except Exception:
                strength = 0.6
            # Keep the highest-strength reading for each theme
            theme_score_by_key[key] = max(theme_score_by_key.get(key, 0.0), strength)

        # 2) Build ETF candidate pool
        candidates = EtfUniverse.by_themes(theme_keys, tradable_only=True)
        if not candidates:
            # Fallback to a balanced default basket so the dashboard is never empty.
            candidates = EtfUniverse.tradable_products()[:6]

        # 3) Forecast each candidate
        forecasts: List[Dict[str, Any]] = []
        market_status: List[Dict[str, Any]] = []
        for product in candidates:
            symbol = product.get("yahoo") or product.get("code")
            rows, status = MarketDataService.fetch_ohlcv(symbol)
            market_status.append({"code": product.get("code"), "status": status})
            if not rows:
                forecasts.append(_empty_forecast(product, reason=status.get("source") or "no_data"))
                continue

            foundation = _foundation_forecast(rows, horizon_days)
            sig = compute_signals(rows, horizon_days=horizon_days, foundation=foundation)
            if not sig.get("ok"):
                forecasts.append(_empty_forecast(product, reason=sig.get("reason", "compute_failed")))
                continue

            backtest = None
            if with_backtest:
                bt = backtest_hit_rate(rows, horizon_days=horizon_days)
                if bt.get("ok"):
                    backtest = bt

            tech_unit = _DIR_SCORE.get(sig["direction"], 0.0) * float(sig.get("confidence") or 0.0)
            theme_score = _best_theme_score(product, theme_score_by_key)
            risk_pen = tier_penalty(product.get("risk_tier"))
            combined = (
                W_THEME * theme_score
                + W_TECH * tech_unit
                + W_RISK * (1.0 - risk_pen)
            )

            forecasts.append({
                "code": product["code"],
                "yahoo": product.get("yahoo"),
                "name_zh": product.get("name_zh"),
                "name_en": product.get("name_en"),
                "asset_class": product.get("asset_class"),
                "risk_tier": product.get("risk_tier"),
                "currency": product.get("currency"),
                "theme_tags": product.get("theme_tags") or [],
                "matched_themes": _matched_themes(product, theme_score_by_key),
                "theme_score": round(theme_score, 3),
                "tech_score": round(tech_unit, 3),
                "risk_penalty": round(risk_pen, 3),
                "combined_score": round(combined, 4),
                "direction": sig["direction"],
                "confidence": sig["confidence"],
                "horizon_days": sig["horizon_days"],
                "expected_return_pct": sig["expected_return_pct"],
                "last_close": sig["last_close"],
                "as_of": sig["as_of"],
                "votes": sig["votes"],
                "indicators_last": sig["indicators_last"],
                "risk": sig["risk"],
                "bars": sig["bars"],
                "backtest": backtest,
                "price_source": sig.get("price_source"),
                "predicted_price": sig.get("predicted_price"),
                "predicted_band": sig.get("predicted_band"),
                "precise_forecast": _format_precise_forecast(foundation),
            })

        # 4) Rank & build allocation
        forecasts.sort(key=lambda f: f.get("combined_score") or -999, reverse=True)
        ranked = [f for f in forecasts if f.get("direction")]  # drop empty rows

        top = ranked[:top_n]
        allocation = _build_allocation(top)

        # 5) KPIs for dashboard header
        kpis = _build_kpis(top, allocation)

        bundle = {
            "bundle_id": f"alloc_{uuid.uuid4().hex[:12]}",
            "report_id": report_id,
            "simulation_id": report.get("simulation_id"),
            "generated_at": _now_iso(),
            "horizon_days": horizon_days,
            "themes_used": [
                {"key": k, "strength": round(v, 3)}
                for k, v in sorted(theme_score_by_key.items(), key=lambda kv: kv[1], reverse=True)
            ],
            "kpis": kpis,
            "forecasts": forecasts,        # all candidates (incl. failed)
            "top_picks": top,              # forecast objects for UI cards
            "allocation": allocation,      # weighted basket with caps
            "sales_brief": _build_sales_brief(top, allocation),
            "market_status": market_status,
            "model_meta": {
                "engine": "rule_indicator_vote_v1+foundation_price",
                "price_engine": _foundation_engine_label(),
                "weights": {"theme": W_THEME, "tech": W_TECH, "risk": W_RISK},
                "indicators": ["SMA20/60", "EMA20", "MACD(12,26,9)",
                               "RSI14", "BollingerBands(20,2)", "ATR14",
                               "Momentum10/20"],
            },
        }
        cls.save_bundle(report_id, bundle)
        return bundle

    # ---- single ETF endpoint helper ---------------------------------

    @classmethod
    def forecast_single(cls, code: str, lookback_days: int = 365, horizon_days: int = 1) -> Dict[str, Any]:
        product = EtfUniverse.by_code(code)
        if not product:
            return {"ok": False, "error": f"unknown_code:{code}"}
        symbol = product.get("yahoo") or product.get("code")
        rows, status = MarketDataService.fetch_ohlcv(symbol, lookback_days=lookback_days)
        if not rows:
            return {"ok": False, "error": "no_data", "status": status, "product": product}
        foundation = _foundation_forecast(rows, horizon_days)
        sig = compute_signals(rows, horizon_days=horizon_days, foundation=foundation)
        bt = backtest_hit_rate(rows, horizon_days=horizon_days)
        return {
            "ok": sig.get("ok", False),
            "product": product,
            "status": status,
            "signal": sig,
            "precise_forecast": _format_precise_forecast(foundation),
            "backtest": bt if bt.get("ok") else None,
            "ohlcv_tail": rows[-90:],   # last ~90 trading days for chart
        }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _empty_forecast(product: Dict[str, Any], reason: str) -> Dict[str, Any]:
    return {
        "code": product["code"],
        "yahoo": product.get("yahoo"),
        "name_zh": product.get("name_zh"),
        "name_en": product.get("name_en"),
        "asset_class": product.get("asset_class"),
        "risk_tier": product.get("risk_tier"),
        "theme_tags": product.get("theme_tags") or [],
        "direction": None,
        "confidence": 0.0,
        "combined_score": -1.0,
        "error": reason,
    }


def _best_theme_score(product: Dict[str, Any], theme_score_by_key: Dict[str, float]) -> float:
    best = 0.0
    for tag in product.get("theme_tags") or []:
        if tag in theme_score_by_key:
            best = max(best, theme_score_by_key[tag])
    return best if best > 0 else 0.3   # baseline so universe doesn't go to 0


def _matched_themes(product: Dict[str, Any], theme_score_by_key: Dict[str, float]) -> List[str]:
    return [t for t in (product.get("theme_tags") or []) if t in theme_score_by_key]


def _build_allocation(top: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Convert ranked picks to a weighted basket honoring per-tier caps."""
    if not top:
        return {"items": [], "total_weight": 0.0, "expected_return_pct": 0.0}

    # Use only items that are not bearish; bearish picks shown as "avoid".
    eligible = [f for f in top if f.get("direction") in ("bullish", "neutral")]
    avoid = [f for f in top if f.get("direction") == "bearish"]

    # Raw weight = max(combined_score, 0.01)
    raw = [(f, max(f.get("combined_score") or 0.0, 0.01)) for f in eligible]
    total_raw = sum(w for _, w in raw) or 1.0

    items: List[Dict[str, Any]] = []
    used = 0.0
    for f, w in raw:
        cap = tier_cap(f.get("risk_tier"))
        weight = min(w / total_raw, cap)
        items.append({
            "code": f["code"],
            "name_zh": f["name_zh"],
            "name_en": f["name_en"],
            "weight": round(weight, 4),
            "direction": f["direction"],
            "confidence": f["confidence"],
            "expected_return_pct": f.get("expected_return_pct"),
            "risk_tier": f.get("risk_tier"),
        })
        used += weight

    # Renormalise so weights sum to 1.0
    if used > 0:
        for it in items:
            it["weight"] = round(it["weight"] / used, 4)

    expected = 0.0
    for it in items:
        ret = (it.get("expected_return_pct") or {}).get("central") or 0.0
        expected += it["weight"] * ret

    return {
        "items": items,
        "total_weight": round(sum(it["weight"] for it in items), 4),
        "expected_return_pct": round(expected, 2),
        "avoid": [
            {"code": f["code"], "name_zh": f["name_zh"], "reason": "bearish_signal"}
            for f in avoid
        ],
    }


def _build_kpis(top: List[Dict[str, Any]], allocation: Dict[str, Any]) -> Dict[str, Any]:
    if not top:
        return {
            "expected_return_pct": 0.0,
            "avg_confidence": 0.0,
            "bullish_count": 0,
            "bearish_count": 0,
            "neutral_count": 0,
            "portfolio_risk_tier": "n/a",
        }
    bullish = sum(1 for f in top if f.get("direction") == "bullish")
    bearish = sum(1 for f in top if f.get("direction") == "bearish")
    neutral = sum(1 for f in top if f.get("direction") == "neutral")
    avg_conf = sum(f.get("confidence") or 0.0 for f in top) / max(len(top), 1)

    # Crude portfolio risk tier = weighted average penalty
    tier_weights = {f["code"]: f.get("risk_penalty", 0.2) for f in top}
    items = allocation.get("items") or []
    if items:
        wpen = sum(it["weight"] * tier_weights.get(it["code"], 0.2) for it in items)
    else:
        wpen = sum(tier_weights.values()) / max(len(tier_weights), 1)
    if wpen < 0.15:
        port_tier = "low"
    elif wpen < 0.25:
        port_tier = "mid"
    elif wpen < 0.4:
        port_tier = "high"
    else:
        port_tier = "very_high"

    return {
        "expected_return_pct": allocation.get("expected_return_pct", 0.0),
        "avg_confidence": round(avg_conf, 3),
        "bullish_count": bullish,
        "bearish_count": bearish,
        "neutral_count": neutral,
        "portfolio_risk_tier": port_tier,
    }


def _build_sales_brief(top: List[Dict[str, Any]], allocation: Dict[str, Any]) -> str:
    if not top:
        return "（暂无可用产品行情数据，无法生成销售要点。）"
    lines = ["【未来 5 个交易日 CSOP ETF 重点推荐】", ""]
    for it in (allocation.get("items") or [])[:5]:
        ret = (it.get("expected_return_pct") or {}).get("central")
        ret_str = f"{ret:+.2f}%" if isinstance(ret, (int, float)) else "—"
        lines.append(
            f"• {it['code']} {it['name_zh']}：建议配置 {it['weight']*100:.1f}%，"
            f"方向 {it['direction']}（置信度 {it['confidence']:.0%}），预期 5 日中枢 {ret_str}。"
        )
    avoid = allocation.get("avoid") or []
    if avoid:
        lines.append("")
        lines.append("【建议规避】")
        for it in avoid[:3]:
            lines.append(f"• {it['code']} {it['name_zh']}：技术信号偏空，建议回避或降仓。")
    lines.append("")
    lines.append("注：上述结果由规则化技术指标投票引擎生成，仅供销售参考，不构成投资建议。")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Foundation forecast adapter (Kronos + Chronos-Bolt)
# ---------------------------------------------------------------------------


def _foundation_forecast(rows: List[Dict[str, Any]], horizon_days: int) -> Optional[Dict[str, Any]]:
    """Run Kronos+Chronos ensemble on OHLCV rows; return None on any failure."""
    try:
        import pandas as pd  # type: ignore
        from ...quant.models.foundation_ensemble import predict_ensemble  # type: ignore
    except Exception as exc:
        logger.debug("foundation_ensemble import failed: %s", exc)
        return None
    try:
        df = pd.DataFrame([
            {
                "open": r.get("open", r.get("close")),
                "high": r.get("high", r.get("close")),
                "low": r.get("low", r.get("close")),
                "close": r.get("close"),
                "volume": r.get("volume", 0.0),
            }
            for r in rows
        ]).dropna(subset=["close"])
        if "date" in (rows[0] if rows else {}):
            df.index = pd.to_datetime([r.get("date") for r in rows[: len(df)]])
        return predict_ensemble(df, horizon=max(1, int(horizon_days)))
    except Exception as exc:  # noqa: BLE001
        logger.warning("foundation_ensemble predict failed: %s", exc)
        return None


def _format_precise_forecast(foundation: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Strip the heavy raw model dicts; keep only display-friendly fields."""
    if not foundation:
        return None
    return {
        "predicted_price": foundation.get("predicted_price"),
        "p10": foundation.get("p10"),
        "p50": foundation.get("p50"),
        "p90": foundation.get("p90"),
        "p_up": foundation.get("p_up"),
        "expected_return": foundation.get("expected_return"),
        "uncertainty": foundation.get("foundation_uncertainty"),
        "cross_model_agreement": foundation.get("cross_model_agreement"),
        "mode": foundation.get("mode"),
        "horizon_days": foundation.get("horizon"),
        "last_close": foundation.get("last_close"),
    }


def _foundation_engine_label() -> str:
    """Best-effort label of which foundation models are actually loaded."""
    try:
        from ...quant.models.foundation_ensemble import get_foundation_status  # type: ignore
        s = get_foundation_status(load=False, run_smoke=False)
        if s.get("available"):
            return s.get("ensemble") or "foundation"
        return "sigma_band_fallback"
    except Exception:
        return "unknown"
