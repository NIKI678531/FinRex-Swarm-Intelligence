"""Shared label utilities for the two towers."""

from __future__ import annotations


def make_direction_label(close, horizon: int):
    """Direction of forward T+horizon close-to-close return.

    Returns a Series of {-1, 0, 1} aligned with ``close.index``; the last
    ``horizon`` rows will be NaN.
    """
    import numpy as np
    fwd = close.shift(-horizon) / close - 1.0
    label = fwd.apply(lambda r: 0 if r != r else (1 if r > 0 else (-1 if r < 0 else 0)))
    # Mask trailing rows where forward return isn't observable.
    label.iloc[-horizon:] = float("nan")
    return label


def train_lightgbm(X, y, **kwargs):
    """Lazy-imported LightGBM trainer for direction classification."""
    import lightgbm as lgb
    import numpy as np
    import pandas as pd

    valid = ~(y.isna() | X.isna().any(axis=1))
    Xv = X[valid]
    yv = y[valid].astype(int)
    if Xv.empty:
        return None
    model = lgb.LGBMClassifier(
        n_estimators=kwargs.get("n_estimators", 300),
        learning_rate=kwargs.get("learning_rate", 0.05),
        max_depth=kwargs.get("max_depth", -1),
        num_leaves=kwargs.get("num_leaves", 31),
        min_data_in_leaf=kwargs.get("min_data_in_leaf", 20),
        objective="multiclass" if yv.nunique() > 2 else "binary",
        verbose=-1,
    )
    # LightGBM needs labels in [0, n_classes); shift.
    classes = sorted(yv.unique().tolist())
    class_to_idx = {c: i for i, c in enumerate(classes)}
    yv_enc = yv.map(class_to_idx)
    model.fit(Xv, yv_enc)
    model._fr_classes = classes  # type: ignore[attr-defined]
    return model


def predict_proba(model, X):
    import numpy as np
    import pandas as pd
    if model is None:
        return pd.Series(0.5, index=X.index)
    classes = getattr(model, "_fr_classes", None) or [-1, 0, 1]
    probs = model.predict_proba(X.fillna(0.0))
    if 1 in classes:
        idx = classes.index(1)
        up = probs[:, idx]
    else:
        up = probs[:, -1]
    return pd.Series(up, index=X.index)
