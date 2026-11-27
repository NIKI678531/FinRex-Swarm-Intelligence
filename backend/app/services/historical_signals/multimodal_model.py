"""Small sklearn-level multimodal predictor for Backtest/Validation.

This is intentionally lightweight: it trains only on prior rows in a
walk-forward loop and falls back to the existing weighted sigmoid when the
sample is too small or sklearn is unavailable.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple


MARKET_KEYS = ["price_momentum", "volatility"]
TEXT_KEYS = ["sentiment_finbert", "sentiment_emotion", "news_volume", "social_volume"]
OASIS_KEYS = [
    "oasis_sentiment",
    "oasis_pulse_score",
    "oasis_risk_intensity",
    "oasis_volume_z",
    "oasis_velocity_z",
    "oasis_consensus",
    "oasis_disagreement",
    "oasis_cross_platform_spread",
    "oasis_fomo_score",
    "oasis_panic_score",
]
FEATURE_GROUPS = {
    "market_only": MARKET_KEYS,
    "market_text": MARKET_KEYS + TEXT_KEYS,
    "market_text_oasis": MARKET_KEYS + TEXT_KEYS + OASIS_KEYS,
}


def sigmoid(x: float) -> float:
    if x >= 50:
        return 1.0
    if x <= -50:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


def weighted_score(row: Dict[str, float], weights: Dict[str, float], keys: Sequence[str]) -> Tuple[float, Dict[str, float]]:
    contrib = {k: float(weights.get(k, 0.0)) * float(row.get(k, 0.0)) for k in keys}
    return sum(contrib.values()), contrib


def predict_weighted(
    norm_rows: List[Dict[str, float]],
    weights: Dict[str, float],
    keys: Sequence[str],
) -> List[Dict[str, Any]]:
    out = []
    for row in norm_rows:
        raw_score, contrib = weighted_score(row, weights, keys)
        conviction = 1.0 / (1.0 + max(0.0, float(row.get("volatility", 0.0))))
        model_score = raw_score * conviction
        p_up = sigmoid(model_score)
        out.append({
            "p_up": p_up,
            "model_score": model_score,
            "feature_contribution": contrib,
            "model_used": "weighted_sigmoid",
        })
    return out


def predict_multimodal_walk_forward(
    norm_rows: List[Dict[str, float]],
    outcomes: List[int],
    weights: Dict[str, float],
    keys: Sequence[str],
    *,
    min_train: int = 60,
) -> List[Dict[str, Any]]:
    weighted = predict_weighted(norm_rows, weights, keys)
    try:
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.linear_model import LogisticRegression
    except Exception:
        return weighted

    out: List[Dict[str, Any]] = []
    for i, row in enumerate(norm_rows):
        if i < min_train or i >= len(outcomes):
            out.append(weighted[i])
            continue
        x_train = [[float(r.get(k, 0.0)) for k in keys] for r in norm_rows[:i]]
        y_train = outcomes[:i]
        if len(set(y_train)) < 2:
            out.append(weighted[i])
            continue
        x_now = [[float(row.get(k, 0.0)) for k in keys]]
        try:
            logit = LogisticRegression(max_iter=250, class_weight="balanced")
            gbdt = GradientBoostingClassifier(random_state=17, n_estimators=45, max_depth=2, learning_rate=0.05)
            logit.fit(x_train, y_train)
            gbdt.fit(x_train, y_train)
            p_logit = float(logit.predict_proba(x_now)[0][1])
            p_gbdt = float(gbdt.predict_proba(x_now)[0][1])
            p_up = max(0.01, min(0.99, 0.45 * p_logit + 0.55 * p_gbdt))
            importances = getattr(gbdt, "feature_importances_", None)
            if importances is not None:
                contrib = {k: float(importances[idx]) * abs(float(row.get(k, 0.0))) for idx, k in enumerate(keys)}
            else:
                contrib = weighted[i]["feature_contribution"]
            out.append({
                "p_up": p_up,
                "model_score": math.log(p_up / max(1e-9, 1.0 - p_up)),
                "feature_contribution": contrib,
                "model_used": "multimodal_v1",
                "p_logit": p_logit,
                "p_gbdt": p_gbdt,
            })
        except Exception:
            out.append(weighted[i])
    return out


def feature_schema() -> Dict[str, Any]:
    return {
        "groups": {
            "market": MARKET_KEYS,
            "text": TEXT_KEYS,
            "oasis": OASIS_KEYS,
        },
        "ablation_modes": list(FEATURE_GROUPS.keys()),
    }

