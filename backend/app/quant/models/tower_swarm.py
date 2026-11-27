"""Swarm Tower — LightGBM over the 8 OASIS behavioural factors.

When sample count is too small (<200 rows) we fall back to a simple
rule-based linear scorer rather than fitting LightGBM, to avoid the
small-sample overfitting trap discussed in plan-finrex-hybrid-alpha §八.
"""

from __future__ import annotations

from ._common import make_direction_label, train_lightgbm, predict_proba

MIN_SAMPLES_FOR_GBM = 200


class SwarmTower:
    def __init__(self):
        self.model = None
        self.feature_cols = None
        self.rule_weights = None  # used in fallback

    def fit(self, features, close, horizon: int = 5):
        import pandas as pd

        X = features.copy()
        self.feature_cols = list(X.columns)
        y = make_direction_label(close, horizon=horizon)
        common = X.index.intersection(y.index)
        Xa = X.loc[common]
        ya = y.loc[common]

        usable = (~Xa.isna().all(axis=1) & ~ya.isna()).sum()
        if usable >= MIN_SAMPLES_FOR_GBM:
            self.model = train_lightgbm(Xa, ya)
        else:
            # Rule-based fallback: equal positive weights on "bullish" factors
            self.rule_weights = pd.Series(
                {c: (1.0 if c in {
                    "sentiment_mean", "sentiment_velocity", "bull_ratio",
                    "consensus_speed", "kol_lead_signal"} else -1.0)
                 for c in self.feature_cols}
            )
        return self

    def predict_proba(self, features):
        import numpy as np
        import pandas as pd

        X = features[self.feature_cols] if self.feature_cols else features
        if self.model is not None:
            return predict_proba(self.model, X)
        # Rule-based: logistic of weighted sum
        if self.rule_weights is None:
            return pd.Series(0.5, index=X.index)
        z = (X.fillna(0.0) * self.rule_weights).sum(axis=1)
        return 1.0 / (1.0 + np.exp(-z))
