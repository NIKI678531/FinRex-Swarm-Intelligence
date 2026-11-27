"""Chronos-Bolt Tower — general-purpose probabilistic time-series forecaster.

Wraps Amazon's `chronos-bolt-small` (zero-shot) for quantile forecasts.
All heavy imports are lazy so the rest of the quant stack stays importable
even when `chronos-forecasting` / `torch` are not installed.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from ..config import (
    CHRONOS_CONTEXT_LEN,
    CHRONOS_ENABLED,
    CHRONOS_MODEL_ID,
)

logger = logging.getLogger(__name__)

_PIPE = None
_LOAD_FAILED = False
_LAST_ERROR: Optional[str] = None
_LOAD_SOURCE: Optional[str] = None


def _load_pipeline():
    global _PIPE, _LOAD_FAILED, _LAST_ERROR, _LOAD_SOURCE
    if _PIPE is not None or _LOAD_FAILED:
        return _PIPE
    if not CHRONOS_ENABLED:
        _LAST_ERROR = "Chronos-Bolt disabled by QUANT_CHRONOS_ENABLED"
        _LOAD_FAILED = True
        return None
    try:
        from chronos import ChronosBoltPipeline  # type: ignore
        import torch  # type: ignore
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _PIPE = ChronosBoltPipeline.from_pretrained(
            CHRONOS_MODEL_ID,
            device_map=device,
            torch_dtype=torch.float32,
        )
        _LOAD_SOURCE = "package:chronos-forecasting"
        _LAST_ERROR = None
        logger.info("Chronos-Bolt loaded: %s on %s", CHRONOS_MODEL_ID, device)
    except Exception as exc:  # noqa: BLE001
        _LAST_ERROR = f"{type(exc).__name__}: {exc}"
        logger.exception("Chronos-Bolt load failed (will fall back to range midpoint): %s", _LAST_ERROR)
        _PIPE = None
        _LOAD_FAILED = True
    return _PIPE


def get_status(load: bool = False) -> Dict[str, Any]:
    if load:
        _load_pipeline()
    return {
        "enabled": bool(CHRONOS_ENABLED),
        "available": _PIPE is not None,
        "load_failed": bool(_LOAD_FAILED),
        "last_error": _LAST_ERROR,
        "source": _LOAD_SOURCE,
        "model_id": CHRONOS_MODEL_ID,
        "context_len": CHRONOS_CONTEXT_LEN,
    }


class ChronosBoltTower:
    """Quantile forecaster. Returns p10/p50/p90 + naive p_up estimate."""

    def __init__(self) -> None:
        self.available = False

    def warmup(self) -> bool:
        self.available = _load_pipeline() is not None
        return self.available

    def predict(
        self,
        close_series: pd.Series,
        horizon: int = 5,
        num_samples: int = 20,
    ) -> Optional[Dict[str, Any]]:
        global _LAST_ERROR
        pipe = _load_pipeline()
        if pipe is None:
            return None
        try:
            import torch  # type: ignore

            s = pd.Series(close_series).dropna().astype(float)
            if len(s) < 32:
                _LAST_ERROR = f"insufficient close rows for Chronos-Bolt: {len(s)} < 32"
                return None
            ctx = s.tail(CHRONOS_CONTEXT_LEN).values
            ctx_tensor = torch.tensor(ctx, dtype=torch.float32)
            try:
                quantiles, mean = pipe.predict_quantiles(
                    inputs=ctx_tensor,
                    prediction_length=horizon,
                    quantile_levels=[0.1, 0.5, 0.9],
                )
            except TypeError:
                quantiles, mean = pipe.predict_quantiles(
                    context=ctx_tensor,
                    prediction_length=horizon,
                    quantile_levels=[0.1, 0.5, 0.9],
                )
            q = quantiles.detach().cpu().numpy()
            if q.ndim == 3:
                q = q[0]
            if q.ndim != 2 or q.shape[-1] < 3:
                _LAST_ERROR = f"unexpected quantile output shape: {q.shape}"
                logger.warning("Chronos unexpected quantile output shape: %s", q.shape)
                return None
            last_close = float(ctx[-1])
            p10 = float(q[-1, 0])
            p50 = float(q[-1, 1])
            p90 = float(q[-1, 2])
            std = float(np.std(q[-1]))
            # Approx probability of upward move at horizon end:
            # 50%-quantile relative to last close, mass above last_close ~ via p10/p90 spread
            if p90 - p10 > 1e-9:
                p_up = float(np.clip((p50 - last_close) / (p90 - p10) + 0.5, 0.0, 1.0))
            else:
                p_up = 0.5
            _LAST_ERROR = None
            return {
                "p10": p10,
                "p50": p50,
                "p90": p90,
                "std": std,
                "p_up": p_up,
                "horizon": horizon,
                "model": CHRONOS_MODEL_ID,
            }
        except Exception as exc:  # noqa: BLE001
            _LAST_ERROR = str(exc)
            logger.warning("Chronos predict failed: %s", exc)
            return None
