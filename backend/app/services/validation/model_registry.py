"""Prediction-model registry for the weekly validation desk.

Mirrors the three model families exposed on the backtest page
(`QuantBacktestLab.vue`) so the validation desk and the backtest lab speak the
exact same language:

    price_point_calibrated_ml  →  "Price Forecast (Calibrated ML)"  (Kronos+Chronos)
    two_tower                  →  "Two-Tower Hybrid Alpha"          (Market+Swarm+Meta)
    financial_forecast         →  "Legacy Financial Signal"         (interpretable composite)

Each entry declares how a model maps onto the weekly Monte-Carlo / analytic
binning pipeline via `output_kind`:
    - "price_dist": forward inference yields a full price distribution
      (p10/p50/p90) → bins computed analytically (lognormal) with an MC cross-check.
    - "direction": forward inference yields a directional probability (p_up)
      → bins computed by biasing the Monte-Carlo drift.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

VALIDATION_MODELS: List[Dict[str, Any]] = [
    {
        "key": "price_point_calibrated_ml",
        "label_en": "Price Forecast (Calibrated ML)",
        "label_zh": "价格预测 (校准ML)",
        "output_kind": "price_dist",
        "description_en": "Kronos + Chronos foundation ensemble with ML calibration; "
                          "forecasts the full weekly price distribution.",
        "description_zh": "Kronos + Chronos 基础模型集成并经 ML 校准，预测完整周度价格分布。",
    },
    {
        "key": "two_tower",
        "label_en": "Two-Tower Hybrid Alpha",
        "label_zh": "双塔混合 Alpha",
        "output_kind": "direction",
        "description_en": "Market Tower + Swarm Tower fused by a meta-model into a "
                          "directional probability.",
        "description_zh": "行情塔 + 群体智能塔经元模型融合，输出方向概率。",
    },
    {
        "key": "financial_forecast",
        "label_en": "Legacy Financial Signal",
        "label_zh": "经典金融信号",
        "output_kind": "direction",
        "description_en": "Interpretable composite of technical / sentiment / volume / "
                          "OASIS pulse factors.",
        "description_zh": "技术 / 情绪 / 量能 / OASIS 脉冲因子的可解释加权合成。",
    },
]

_BY_KEY: Dict[str, Dict[str, Any]] = {m["key"]: m for m in VALIDATION_MODELS}

DEFAULT_MODEL_KEY = "price_point_calibrated_ml"


def list_models() -> List[Dict[str, Any]]:
    """Return the public model catalogue (safe to serialize to the frontend)."""
    return [dict(m) for m in VALIDATION_MODELS]


def is_valid_model(model_family: Optional[str]) -> bool:
    return bool(model_family) and model_family in _BY_KEY


def resolve_model(model_family: Optional[str]) -> Dict[str, Any]:
    """Return the model spec, falling back to the default when unknown."""
    if model_family and model_family in _BY_KEY:
        return dict(_BY_KEY[model_family])
    return dict(_BY_KEY[DEFAULT_MODEL_KEY])


def output_kind(model_family: Optional[str]) -> str:
    return resolve_model(model_family).get("output_kind", "direction")
