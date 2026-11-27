"""Synthetic OHLCV fixture for quant tests — no network required."""

from __future__ import annotations

import numpy as np
import pandas as pd


def make_synthetic_ohlcv(n: int = 800, seed: int = 7, start: str = "2020-01-01") -> pd.DataFrame:
    """Generate a deterministic, slightly trending OHLCV frame.

    Returned index is tz-aware UTC daily timestamps with columns
    [open, high, low, close, volume].
    """
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start=start, periods=n, freq="1D", tz="UTC")
    # Random walk with mild upward drift
    rets = rng.normal(loc=0.0005, scale=0.015, size=n)
    close = 100.0 * np.exp(np.cumsum(rets))
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) * (1.0 + np.abs(rng.normal(0, 0.005, n)))
    low = np.minimum(open_, close) * (1.0 - np.abs(rng.normal(0, 0.005, n)))
    volume = rng.lognormal(mean=12.0, sigma=0.3, size=n)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )
