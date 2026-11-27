"""Meta-Model — fuses tower probabilities with market state features.

Inputs: ``[P_market, P_swarm, vol_5d, vol_20d, volume_z, event_flag]``.
Output: P_final (probability of an upward move).

To prevent overfitting on a 6-D input space we use shallow learners only.
"""

from __future__ import annotations


class MetaModel:
    def __init__(self, kind: str = "logreg"):
        self.kind = kind
        self.model = None
        self.feature_cols = [
            "p_market", "p_swarm", "vol_5d", "vol_20d", "volume_z", "event_flag",
        ]

    def fit(self, df_inputs, y_direction):
        import lightgbm as lgb
        from sklearn.linear_model import LogisticRegression

        X = df_inputs[self.feature_cols].fillna(0.0)
        # Reduce to binary up vs not-up
        y = (y_direction > 0).astype(int)
        common = X.index.intersection(y.index)
        valid = ~y.loc[common].isna()
        Xa = X.loc[common][valid]
        ya = y.loc[common][valid]
        if Xa.empty:
            return self
        if self.kind == "gbm":
            self.model = lgb.LGBMClassifier(
                n_estimators=200, max_depth=3, num_leaves=8,
                learning_rate=0.05, min_data_in_leaf=10, verbose=-1,
            )
        else:
            self.model = LogisticRegression(max_iter=500)
        self.model.fit(Xa, ya)
        return self

    def predict_proba(self, df_inputs):
        import pandas as pd
        X = df_inputs[self.feature_cols].fillna(0.0)
        if self.model is None:
            return pd.Series(0.5, index=X.index)
        probs = self.model.predict_proba(X)
        return pd.Series(probs[:, 1], index=X.index)
