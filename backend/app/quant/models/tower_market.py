"""Market Tower — LightGBM over price/volume technical features."""

from __future__ import annotations

from ._common import make_direction_label, train_lightgbm, predict_proba


class MarketTower:
    """Thin wrapper holding a single trained LightGBM model."""

    def __init__(self):
        self.model = None
        self.feature_cols = None

    def fit(self, features, close, horizon: int = 5):
        X = features.copy()
        self.feature_cols = list(X.columns)
        y = make_direction_label(close, horizon=horizon)
        # Align on common index
        common = X.index.intersection(y.index)
        self.model = train_lightgbm(X.loc[common], y.loc[common])
        return self

    def predict_proba(self, features):
        X = features[self.feature_cols] if self.feature_cols else features
        return predict_proba(self.model, X)
