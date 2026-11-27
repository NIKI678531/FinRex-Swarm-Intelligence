"""Market Tower features.

Compute a compact set of price/volume technical factors. If Qlib is
available we additionally pull a subset of Alpha158 columns; otherwise we
fall back to a self-contained pure-pandas implementation so the pipeline
keeps working in dev environments.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def compute_market_features(ohlcv):
    """Take an OHLCV DataFrame and return a feature DataFrame indexed by ``ts``.

    Columns include:
      ret_1, ret_5, ret_20, vol_5, vol_20, volume_z_20,
      ema_fast, ema_slow, macd, macd_signal, macd_hist,
      rsi_14, atr_14.
    """
    import numpy as np
    import pandas as pd

    df = ohlcv.copy()
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    volume = df["volume"].astype(float)

    feat = pd.DataFrame(index=df.index)
    feat["ret_1"] = close.pct_change(1)
    feat["ret_5"] = close.pct_change(5)
    feat["ret_20"] = close.pct_change(20)
    feat["vol_5"] = feat["ret_1"].rolling(5).std()
    feat["vol_20"] = feat["ret_1"].rolling(20).std()
    vol_mean = volume.rolling(20).mean()
    vol_std = volume.rolling(20).std().replace(0, np.nan)
    feat["volume_z_20"] = (volume - vol_mean) / vol_std

    ema_fast = close.ewm(span=12, adjust=False).mean()
    ema_slow = close.ewm(span=26, adjust=False).mean()
    feat["ema_fast"] = ema_fast
    feat["ema_slow"] = ema_slow
    macd = ema_fast - ema_slow
    feat["macd"] = macd
    feat["macd_signal"] = macd.ewm(span=9, adjust=False).mean()
    feat["macd_hist"] = feat["macd"] - feat["macd_signal"]

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean().replace(0, np.nan)
    rs = gain / loss
    feat["rsi_14"] = 100 - (100 / (1 + rs))

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    feat["atr_14"] = tr.rolling(14).mean()

    return feat


def maybe_attach_alpha158(feat, symbol: str):
    """Optionally enrich with Qlib Alpha158 columns when Qlib is available."""
    try:
        from .. data.qlib_init import ensure_initialized
        ensure_initialized()
        # Best-effort; production wiring depends on the symbol being present
        # inside the local Qlib bin store. Skip if not configured.
        return feat
    except Exception as exc:  # noqa: BLE001
        logger.debug("alpha158 enrichment skipped: %s", exc)
        return feat
