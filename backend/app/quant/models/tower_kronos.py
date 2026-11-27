"""Kronos Tower — domain-specific OHLCV foundation model.

Wraps `NeoQuasar/Kronos-small` (AAAI 2026) — a 25M-param financial-foundation
model that takes OHLCV context and samples future price paths. Used as the
**primary source of precise price point estimates**.

All heavy imports are lazy. If the model cannot be loaded the tower silently
becomes unavailable and the ensemble falls back to Chronos-Bolt only.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

from ..config import (
    KRONOS_CONTEXT_LEN,
    KRONOS_ENABLED,
    KRONOS_MODEL_ID,
    KRONOS_NUM_SAMPLES,
    KRONOS_TOKENIZER_ID,
)

logger = logging.getLogger(__name__)

_PIPE = None
_LOAD_FAILED = False
_LOAD_SOURCE: Optional[str] = None
_LAST_ERROR: Optional[str] = None


def _import_kronos_classes() -> Tuple[Any, Any, Any, str]:
    """Import Kronos classes from an installed package or the bundled source tree."""
    try:
        from kronos import Kronos, KronosTokenizer, KronosPredictor  # type: ignore

        return Kronos, KronosTokenizer, KronosPredictor, "package:kronos"
    except Exception as package_exc:  # noqa: BLE001
        local_root = Path(__file__).resolve().parents[4] / "Kronos"
        local_model = local_root / "model" / "__init__.py"
        if not local_model.exists():
            raise RuntimeError(
                f"installed kronos import failed ({package_exc}); bundled Kronos source not found at {local_model}"
            ) from package_exc

        import importlib
        import sys

        local_root_str = str(local_root)
        if local_root_str not in sys.path:
            sys.path.insert(0, local_root_str)
        try:
            model_module = importlib.import_module("model")
            return (
                getattr(model_module, "Kronos"),
                getattr(model_module, "KronosTokenizer"),
                getattr(model_module, "KronosPredictor"),
                f"bundled:{local_model.parent}",
            )
        except Exception as local_exc:  # noqa: BLE001
            raise RuntimeError(
                f"installed kronos import failed ({package_exc}); bundled Kronos import failed ({local_exc})"
            ) from local_exc


def _load_pipeline():
    global _PIPE, _LOAD_FAILED, _LOAD_SOURCE, _LAST_ERROR
    if _PIPE is not None or _LOAD_FAILED:
        return _PIPE
    if not KRONOS_ENABLED:
        _LAST_ERROR = "Kronos disabled by QUANT_KRONOS_ENABLED"
        _LOAD_FAILED = True
        return None
    try:
        import torch  # type: ignore

        Kronos, KronosTokenizer, KronosPredictor, source = _import_kronos_classes()
        device = "cuda" if torch.cuda.is_available() else "cpu"
        tokenizer = KronosTokenizer.from_pretrained(KRONOS_TOKENIZER_ID)
        model = Kronos.from_pretrained(KRONOS_MODEL_ID)
        _PIPE = KronosPredictor(model, tokenizer, device=device, max_context=KRONOS_CONTEXT_LEN)
        _LOAD_SOURCE = source
        _LAST_ERROR = None
        logger.info("Kronos loaded: %s + %s on %s from %s", KRONOS_MODEL_ID, KRONOS_TOKENIZER_ID, device, source)
    except Exception as exc:  # noqa: BLE001
        _LAST_ERROR = f"{type(exc).__name__}: {exc}"
        logger.exception("Kronos load failed (will fall back to range midpoint): %s", _LAST_ERROR)
        _PIPE = None
        _LOAD_FAILED = True
    return _PIPE


def get_status(load: bool = False) -> Dict[str, Any]:
    if load:
        _load_pipeline()
    return {
        "enabled": bool(KRONOS_ENABLED),
        "available": _PIPE is not None,
        "load_failed": bool(_LOAD_FAILED),
        "last_error": _LAST_ERROR,
        "source": _LOAD_SOURCE,
        "model_id": KRONOS_MODEL_ID,
        "tokenizer_id": KRONOS_TOKENIZER_ID,
        "context_len": KRONOS_CONTEXT_LEN,
        "num_samples": KRONOS_NUM_SAMPLES,
    }


class KronosTower:
    """OHLCV foundation model. Returns predicted_price + quantile band + paths."""

    def __init__(self) -> None:
        self.available = False

    def warmup(self) -> bool:
        self.available = _load_pipeline() is not None
        return self.available

    def predict(
        self,
        ohlcv_df: pd.DataFrame,
        horizon: int = 5,
        num_samples: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Args:
            ohlcv_df: DataFrame indexed by date, columns including
                open/high/low/close/volume (case-insensitive).
            horizon: forecast horizon (days).
            num_samples: Monte-Carlo path samples. Default from config; CPU
                automatically halves.
        Returns:
            dict with predicted_price (p50), p10/p50/p90, paths, p_up,
            uncertainty, or None on failure.
        """
        global _LAST_ERROR
        pipe = _load_pipeline()
        if pipe is None:
            return None
        try:
            import torch  # type: ignore

            df = ohlcv_df.copy()
            df.columns = [c.lower() for c in df.columns]
            needed = {"open", "high", "low", "close", "volume"}
            missing = needed - set(df.columns)
            if missing:
                _LAST_ERROR = f"missing OHLCV columns: {sorted(missing)}"
                logger.warning("Kronos missing OHLCV cols: %s", missing)
                return None
            df = df[["open", "high", "low", "close", "volume"]].dropna()
            if len(df) < 64:
                _LAST_ERROR = f"insufficient OHLCV rows for Kronos: {len(df)} < 64"
                return None
            ctx = df.tail(KRONOS_CONTEXT_LEN).copy()

            if not isinstance(ctx.index, pd.DatetimeIndex):
                try:
                    ctx.index = pd.to_datetime(ctx.index)
                except Exception:
                    ctx.index = pd.date_range(end=pd.Timestamp.utcnow().normalize(), periods=len(ctx), freq="D")
            x_timestamp = pd.Series(ctx.index)
            last_ts = ctx.index[-1]
            y_timestamp = pd.Series(pd.bdate_range(start=last_ts + pd.Timedelta(days=1), periods=horizon))

            ns = num_samples or KRONOS_NUM_SAMPLES
            if not torch.cuda.is_available():
                ns = max(4, ns // 4)

            close_paths = []
            for _ in range(ns):
                pred_df = pipe.predict(
                    df=ctx,
                    x_timestamp=x_timestamp,
                    y_timestamp=y_timestamp,
                    pred_len=horizon,
                    sample_count=1,
                    verbose=False,
                )
                close_paths.append(pred_df["close"].values)
            paths = np.asarray(close_paths)
            if paths.ndim != 2:
                logger.warning("Kronos unexpected output shape: %s", paths.shape)
                return None
            last_step = paths[:, -1]
            last_close = float(ctx["close"].iloc[-1])
            p10 = float(np.quantile(last_step, 0.10))
            p50 = float(np.quantile(last_step, 0.50))
            p90 = float(np.quantile(last_step, 0.90))
            std = float(np.std(last_step))
            p_up = float((last_step > last_close).mean())
            _LAST_ERROR = None
            return {
                "predicted_price": p50,
                "p10": p10,
                "p50": p50,
                "p90": p90,
                "std": std,
                "p_up": p_up,
                "horizon": horizon,
                "num_samples": int(paths.shape[0]),
                "model": KRONOS_MODEL_ID,
                "last_close": last_close,
            }
        except Exception as exc:  # noqa: BLE001
            _LAST_ERROR = str(exc)
            logger.warning("Kronos predict failed: %s", exc)
            return None
