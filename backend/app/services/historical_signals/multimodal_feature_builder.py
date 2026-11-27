"""Feature assembly for Market + Text + OASIS backtests.

The builder keeps raw daily features and normalized model features separate so
Backtest, Validation, and future online prediction code can share the same
schema instead of rebuilding ad-hoc dictionaries in each caller.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, List, Optional

from .oasis_factor_builder import OASIS_FACTOR_KEYS, neutral_oasis_factors


BASE_FEATURE_KEYS = [
    "sentiment_finbert",
    "sentiment_emotion",
    "news_volume",
    "social_volume",
    "price_momentum",
    "volatility",
]
ALL_FEATURE_KEYS = BASE_FEATURE_KEYS + OASIS_FACTOR_KEYS


def _zscore(values: List[float]) -> List[float]:
    if not values:
        return []
    n = len(values)
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / max(n - 1, 1)
    sd = math.sqrt(var) if var > 0 else 0.0
    if sd == 0:
        return [0.0] * n
    return [(v - mean) / sd for v in values]


class MultimodalFeatureBuilder:
    @staticmethod
    def build_features(
        sentiment_rows: List[Dict[str, Any]],
        market_rows: List[Dict[str, Any]],
        oasis_rows_by_date: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> List[Dict[str, Any]]:
        sent_by_day = {row["date"]: row for row in sentiment_rows}
        oasis_rows_by_date = oasis_rows_by_date or {}
        rows: List[Dict[str, Any]] = []
        closes: List[float] = []

        for bar in market_rows:
            ts = datetime.fromisoformat(bar["ts"])
            day = ts.strftime("%Y-%m-%d")
            sentiment = sent_by_day.get(day, {})
            oasis = {**neutral_oasis_factors(), **(oasis_rows_by_date.get(day) or {})}
            closes.append(bar["close"])

            if len(closes) >= 6 and closes[-6] > 0:
                momentum = (closes[-1] - closes[-6]) / closes[-6]
            else:
                momentum = 0.0

            if len(closes) >= 11:
                window = closes[-11:]
                rets = [(window[i] - window[i - 1]) / window[i - 1] for i in range(1, len(window)) if window[i - 1]]
                mean = sum(rets) / len(rets) if rets else 0.0
                var = sum((ret - mean) ** 2 for ret in rets) / max(len(rets) - 1, 1) if rets else 0.0
                volatility = math.sqrt(var) if var > 0 else 0.0
            else:
                volatility = 0.0

            row = {
                "ts": bar["ts"],
                "date": day,
                "close": bar["close"],
                "sentiment_finbert": float(sentiment.get("sentiment_finbert", 0.0)),
                "sentiment_emotion": float(sentiment.get("sentiment_emotion", 0.0)),
                "news_volume": float(sentiment.get("news_volume", 0)),
                "social_volume": float(sentiment.get("social_volume", 0)),
                "price_momentum": float(momentum),
                "volatility": float(volatility),
            }
            for key in OASIS_FACTOR_KEYS:
                row[key] = float(oasis.get(key, 0.0))
            rows.append(row)

        return rows

    @staticmethod
    def normalize_features(features: List[Dict[str, Any]]) -> List[Dict[str, float]]:
        cols = {key: _zscore([float(row.get(key, 0.0)) for row in features]) for key in ALL_FEATURE_KEYS}
        return [{key: cols[key][idx] for key in ALL_FEATURE_KEYS} for idx in range(len(features))]
