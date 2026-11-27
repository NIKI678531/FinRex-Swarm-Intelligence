"""Foundation Ensemble — fuses Kronos (precise price) + Chronos-Bolt (robust band).

Strategy:
- predicted_price = Kronos.p50 (financial-domain SOTA)
- quantile band  = conservative intersection (wider of the two p10/p90 endpoints)
- cross_model_agreement = correlation between Kronos.p50 trajectory and
  Chronos.p50 sample; if only one model available, returns NaN.
- p_up = mean of the two models' p_up
- foundation_uncertainty = average normalized std

If both models fail, returns None and callers must fall back to legacy
`target_price_range` only.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import math
import numpy as np
import pandas as pd

from ..config import FOUNDATION_ENSEMBLE
from .tower_chronos import ChronosBoltTower
from .tower_chronos import get_status as get_chronos_status
from .tower_kronos import KronosTower
from .tower_kronos import get_status as get_kronos_status

logger = logging.getLogger(__name__)

_KRONOS: Optional[KronosTower] = None
_CHRONOS: Optional[ChronosBoltTower] = None
_LAST_ENSEMBLE_ERROR: Optional[str] = None


def _get_towers():
    global _KRONOS, _CHRONOS
    if _KRONOS is None:
        _KRONOS = KronosTower()
        _KRONOS.warmup()
    if _CHRONOS is None:
        _CHRONOS = ChronosBoltTower()
        _CHRONOS.warmup()
    return _KRONOS, _CHRONOS


def predict_ensemble(
    ohlcv_df: pd.DataFrame,
    horizon: int = 5,
) -> Optional[Dict[str, Any]]:
    """Return unified forecast or None.

    Output keys:
        predicted_price, p10, p50, p90, p_up, foundation_uncertainty,
        cross_model_agreement, kronos, chronos, mode
    """
    global _LAST_ENSEMBLE_ERROR
    if FOUNDATION_ENSEMBLE == "none":
        _LAST_ENSEMBLE_ERROR = "Foundation ensemble disabled by QUANT_FOUNDATION_ENSEMBLE=none"
        return None
    kronos, chronos = _get_towers()
    df = ohlcv_df.copy()
    df.columns = [c.lower() for c in df.columns]
    close = df.get("close")
    if close is None or len(close.dropna()) < 32:
        rows = 0 if close is None else len(close.dropna())
        _LAST_ENSEMBLE_ERROR = f"insufficient close rows for foundation ensemble: {rows} < 32"
        return None

    use_kronos = FOUNDATION_ENSEMBLE in ("kronos+chronos", "kronos_only")
    use_chronos = FOUNDATION_ENSEMBLE in ("kronos+chronos", "chronos_only")

    k = kronos.predict(df, horizon=horizon) if use_kronos else None
    c = chronos.predict(close, horizon=horizon) if use_chronos else None

    if k is None and c is None:
        _LAST_ENSEMBLE_ERROR = summarize_unavailable_reason()
        return None

    last_close = float(close.dropna().iloc[-1])

    if k and c:
        predicted = k["predicted_price"]
        # Conservative band: wider envelope of the two
        p10 = min(k["p10"], c["p10"])
        p90 = max(k["p90"], c["p90"])
        p50 = (k["p50"] + c["p50"]) / 2.0
        p_up = (k["p_up"] + c["p_up"]) / 2.0
        # agreement = 1 - normalized abs diff of p50
        denom = max(abs(k["p50"]), abs(c["p50"]), 1e-9)
        agreement = float(max(0.0, 1.0 - abs(k["p50"] - c["p50"]) / denom))
        unc = (k.get("std", 0.0) + c.get("std", 0.0)) / 2.0 / max(abs(last_close), 1.0)
        mode = "kronos+chronos"
    elif k:
        predicted = k["predicted_price"]
        p10, p50, p90 = k["p10"], k["p50"], k["p90"]
        p_up = k["p_up"]
        agreement = float("nan")
        unc = k.get("std", 0.0) / max(abs(last_close), 1.0)
        mode = "kronos_only"
    else:
        predicted = c["p50"]
        p10, p50, p90 = c["p10"], c["p50"], c["p90"]
        p_up = c["p_up"]
        agreement = float("nan")
        unc = c.get("std", 0.0) / max(abs(last_close), 1.0)
        mode = "chronos_only"

    _LAST_ENSEMBLE_ERROR = None
    return {
        "predicted_price": float(predicted),
        "p10": float(p10),
        "p50": float(p50),
        "p90": float(p90),
        "p_up": float(p_up),
        "foundation_uncertainty": float(unc),
        "cross_model_agreement": None if (isinstance(agreement, float) and math.isnan(agreement)) else float(agreement),
        "expected_return": float((predicted - last_close) / last_close) if last_close else 0.0,
        "horizon": int(horizon),
        "mode": mode,
        "last_close": last_close,
        "kronos": k,
        "chronos": c,
        "model_status": get_foundation_status(load=False, run_smoke=False),
    }


def is_available() -> bool:
    if FOUNDATION_ENSEMBLE == "none":
        return False
    kronos, chronos = _get_towers()
    return kronos.available or chronos.available


def summarize_unavailable_reason() -> str:
    reasons = []
    for name, status in (("Kronos", get_kronos_status(load=False)), ("Chronos-Bolt", get_chronos_status(load=False))):
        if not status.get("enabled"):
            reasons.append(f"{name} disabled")
        elif status.get("available"):
            last_error = status.get("last_error")
            if last_error:
                reasons.append(f"{name} produced no forecast: {last_error}")
            else:
                reasons.append(f"{name} produced no forecast")
        else:
            last_error = status.get("last_error")
            reasons.append(f"{name} unavailable: {last_error or 'not loaded'}")
    if _LAST_ENSEMBLE_ERROR and _LAST_ENSEMBLE_ERROR not in reasons:
        reasons.append(_LAST_ENSEMBLE_ERROR)
    return "; ".join([r for r in reasons if r]) or "Foundation ensemble produced no forecast"


def _build_smoke_ohlcv(rows: int = 90) -> pd.DataFrame:
    idx = pd.date_range(end=pd.Timestamp.utcnow().normalize(), periods=rows, freq="B")
    base = np.linspace(100.0, 112.0, rows)
    wiggle = np.sin(np.linspace(0, 8, rows)) * 1.2
    close = base + wiggle
    return pd.DataFrame(
        {
            "open": close * 0.998,
            "high": close * 1.012,
            "low": close * 0.988,
            "close": close,
            "volume": np.linspace(1_000_000, 1_250_000, rows),
        },
        index=idx,
    )


def get_foundation_status(load: bool = False, run_smoke: bool = False) -> Dict[str, Any]:
    status: Dict[str, Any] = {
        "ensemble": FOUNDATION_ENSEMBLE,
        "last_error": _LAST_ENSEMBLE_ERROR,
        "kronos": get_kronos_status(load=load),
        "chronos": get_chronos_status(load=load),
    }
    status["available"] = bool(status["kronos"].get("available") or status["chronos"].get("available"))
    if run_smoke:
        try:
            forecast = predict_ensemble(_build_smoke_ohlcv(), horizon=5)
            status["smoke"] = {
                "ok": forecast is not None,
                "mode": None if forecast is None else forecast.get("mode"),
                "predicted_price": None if forecast is None else forecast.get("predicted_price"),
                "error": None if forecast is not None else summarize_unavailable_reason(),
            }
        except Exception as exc:  # noqa: BLE001
            status["smoke"] = {"ok": False, "error": str(exc)}
    else:
        status["smoke"] = {"ok": None, "skipped": True}
    return status
