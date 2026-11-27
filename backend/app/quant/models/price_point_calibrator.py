"""ML calibration helpers for Kronos/Chronos price-point forecasts.

The foundation ensemble remains the base forecaster. This module adds the
supervised residual/quantile layer used by walk-forward backtests and by live
reports when a matching calibration artifact exists.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import pickle
import re
from pathlib import Path
from typing import Any, Optional

from .. import config

MODEL_VERSION = "price_point_calibrated_ml_v1"

SWARM_FEATURES = [
    "sentiment_mean",
    "sentiment_velocity",
    "polarization",
    "consensus_speed",
    "bull_ratio",
    "topic_switch_rate",
    "kol_lead_signal",
    "event_intensity",
]

FEATURE_COLUMNS = [
    "raw_expected_return",
    "raw_band_width",
    "raw_p_up",
    "foundation_uncertainty",
    "cross_model_agreement",
    "ret_1",
    "ret_3",
    "ret_5",
    "ret_14",
    "vol_5",
    "vol_20",
    "vol_60",
    "volume_z_20",
    "drawdown_60",
    "rsi_14",
    "macd",
    "macd_signal",
    "macd_hist",
    "range_pct",
    "overnight_gap",
    "asset_crypto",
    "asset_stock",
    "asset_etf",
    "mode_kronos_chronos",
    "mode_kronos_only",
    "mode_chronos_only",
    "mode_fallback",
] + [f"swarm_{name}" for name in SWARM_FEATURES]

_FOUNDATION_DISABLED_REASON: Optional[str] = None


def canonical_symbol(symbol: str | None) -> str:
    raw = str(symbol or "").strip().upper()
    aliases = {
        "BTC": "BTC-USDT",
        "BTCUSD": "BTC-USDT",
        "BTCUSDT": "BTC-USDT",
        "BTC-USD": "BTC-USDT",
        "ETH": "ETH-USDT",
        "ETHUSD": "ETH-USDT",
        "ETHUSDT": "ETH-USDT",
        "ETH-USD": "ETH-USDT",
    }
    return aliases.get(raw, raw)


def infer_asset_class(symbol: str | None) -> str:
    canonical = canonical_symbol(symbol)
    try:
        from ..data import symbol_registry

        return symbol_registry.get(canonical).asset_class
    except Exception:
        if canonical.endswith("-USDT") or canonical in {"BTC", "ETH"}:
            return "crypto"
        if canonical.endswith(".HK"):
            return "hk_stock"
        if canonical.endswith(".SH") or canonical.endswith(".SZ"):
            return "a_stock"
        return "us_stock"


def artifact_dir(symbol: str | None, horizon: int) -> Path:
    key = re.sub(r"[^A-Za-z0-9_.-]+", "_", canonical_symbol(symbol) or "UNKNOWN")
    return config.PRICE_CALIBRATION_DIR / key / f"h{max(1, int(horizon or 1))}"


def latest_artifact_path(symbol: str | None, horizon: int) -> Path:
    return artifact_dir(symbol, horizon) / "latest.json"


def load_latest_artifact(symbol: str | None, horizon: int) -> Optional[dict]:
    fp = latest_artifact_path(symbol, horizon)
    if not fp.exists():
        return None
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return None


def foundation_or_fallback_forecast(
    ohlcv,
    horizon: int = 5,
    *,
    use_foundation: bool = True,
    skip_reason: str | None = None,
) -> tuple[dict, Optional[str]]:
    """Return a raw foundation forecast or a volatility/quantile fallback.

    Once the foundation ensemble proves unavailable, the process keeps using
    the deterministic fallback for subsequent backtest bars to avoid repeated
    slow load attempts.
    """
    global _FOUNDATION_DISABLED_REASON
    horizon = max(1, int(horizon or 1))
    if not use_foundation:
        reason = skip_reason or "Foundation inference skipped by interactive price backtest policy."
        return volatility_quantile_forecast(ohlcv, horizon, reason), reason
    if _FOUNDATION_DISABLED_REASON:
        return volatility_quantile_forecast(ohlcv, horizon, _FOUNDATION_DISABLED_REASON), _FOUNDATION_DISABLED_REASON
    try:
        from .foundation_ensemble import predict_ensemble, summarize_unavailable_reason

        forecast = predict_ensemble(ohlcv, horizon=horizon)
        if forecast:
            return forecast, None
        reason = summarize_unavailable_reason()
        _FOUNDATION_DISABLED_REASON = reason
        return volatility_quantile_forecast(ohlcv, horizon, reason), reason
    except Exception as exc:  # noqa: BLE001
        reason = f"Kronos/Chronos-Bolt unavailable: {exc}"
        _FOUNDATION_DISABLED_REASON = reason
        return volatility_quantile_forecast(ohlcv, horizon, reason), reason


def volatility_quantile_forecast(ohlcv, horizon: int, reason: str = "") -> dict:
    import numpy as np

    close = ohlcv["close"].astype(float).dropna()
    if close.empty:
        last = 0.0
        expected = 0.0
        sigma = 0.0
    else:
        last = float(close.iloc[-1])
        ret = close.pct_change().dropna()
        lookback = ret.tail(min(90, max(20, len(ret))))
        mu = float(lookback.mean()) if len(lookback) else 0.0
        sigma = float(lookback.std(ddof=0)) if len(lookback) else 0.0
        expected = mu * max(1, int(horizon or 1))
        sigma = sigma * math.sqrt(max(1, int(horizon or 1)))
    z80 = 1.2815515655446004
    p50 = last * (1.0 + expected)
    p10 = last * (1.0 + expected - z80 * sigma)
    p90 = last * (1.0 + expected + z80 * sigma)
    p_up = _normal_cdf(expected / max(sigma, 1e-9)) if sigma > 0 else 0.5
    return {
        "predicted_price": float(p50),
        "p10": float(min(p10, p90)),
        "p50": float(p50),
        "p90": float(max(p10, p90)),
        "p_up": float(max(0.01, min(0.99, p_up))),
        "expected_return": float(expected),
        "foundation_uncertainty": float(sigma),
        "cross_model_agreement": None,
        "horizon": int(horizon),
        "last_close": float(last),
        "mode": "volatility_quantile_fallback",
        "warning": reason or "Foundation ensemble unavailable; using volatility/quantile fallback.",
        "model_status": {"available": False, "fallback": True},
    }


def build_feature_row(
    ohlcv,
    raw_forecast: dict,
    *,
    symbol: str | None = None,
    asset_class: str | None = None,
    swarm_row: Any = None,
) -> dict:
    import numpy as np

    df = ohlcv.copy()
    df.columns = [str(c).lower() for c in df.columns]
    close = df["close"].astype(float).dropna()
    high = df.get("high", close).astype(float).reindex(close.index)
    low = df.get("low", close).astype(float).reindex(close.index)
    open_ = df.get("open", close).astype(float).reindex(close.index)
    volume = df.get("volume")
    volume = volume.astype(float).reindex(close.index) if volume is not None else None

    last = float(close.iloc[-1]) if len(close) else _safe_float(raw_forecast.get("last_close"), 0.0)
    prev = float(close.iloc[-2]) if len(close) >= 2 else last
    ret = close.pct_change()
    raw_pred = _safe_float(raw_forecast.get("predicted_price"), last)
    raw_p10 = _safe_float(raw_forecast.get("p10"), raw_pred)
    raw_p90 = _safe_float(raw_forecast.get("p90"), raw_pred)
    raw_expected = _safe_float(raw_forecast.get("expected_return"))
    if raw_expected is None and last:
        raw_expected = raw_pred / last - 1.0

    asset = (asset_class or infer_asset_class(symbol)).lower()
    mode = str(raw_forecast.get("mode") or "").lower().replace("+", "_").replace("-", "_")
    macd, macd_signal, macd_hist = _macd(close)
    row = {
        "raw_expected_return": raw_expected,
        "raw_band_width": (raw_p90 - raw_p10) / max(abs(last), 1e-9),
        "raw_p_up": _safe_float(raw_forecast.get("p_up"), 0.5),
        "foundation_uncertainty": _safe_float(
            raw_forecast.get("foundation_uncertainty", raw_forecast.get("uncertainty")), 0.0
        ),
        "cross_model_agreement": _safe_float(raw_forecast.get("cross_model_agreement"), 0.0),
        "ret_1": _period_return(close, 1),
        "ret_3": _period_return(close, 3),
        "ret_5": _period_return(close, 5),
        "ret_14": _period_return(close, 14),
        "vol_5": _rolling_std(ret, 5),
        "vol_20": _rolling_std(ret, 20),
        "vol_60": _rolling_std(ret, 60),
        "volume_z_20": _volume_z(volume, 20),
        "drawdown_60": _drawdown(close, 60),
        "rsi_14": _rsi(close, 14),
        "macd": macd,
        "macd_signal": macd_signal,
        "macd_hist": macd_hist,
        "range_pct": (
            (float(high.iloc[-1]) - float(low.iloc[-1])) / max(abs(last), 1e-9)
            if len(high) and len(low) else 0.0
        ),
        "overnight_gap": (float(open_.iloc[-1]) / prev - 1.0) if prev else 0.0,
        "asset_crypto": 1.0 if "crypto" in asset else 0.0,
        "asset_stock": 1.0 if "stock" in asset or asset in {"us_stock", "a_stock", "hk_stock"} else 0.0,
        "asset_etf": 1.0 if "etf" in asset else 0.0,
        "mode_kronos_chronos": 1.0 if "kronos_chronos" in mode else 0.0,
        "mode_kronos_only": 1.0 if mode == "kronos_only" else 0.0,
        "mode_chronos_only": 1.0 if mode == "chronos_only" else 0.0,
        "mode_fallback": 1.0 if "fallback" in mode else 0.0,
    }
    for name in SWARM_FEATURES:
        row[f"swarm_{name}"] = _safe_float(_get(swarm_row, name), 0.0)
    return {col: _finite(row.get(col), 0.0) for col in FEATURE_COLUMNS}


def train_residual_model(X, y):
    return _train_regressor(X, y, kind="residual")


def train_quantile_model(X, y, alpha: float):
    return _train_regressor(X, y, kind="quantile", alpha=alpha)


def predict_model(model: Any, feature_row: dict) -> Optional[float]:
    if model is None:
        return None
    try:
        import pandas as pd

        X = pd.DataFrame([{col: _finite(feature_row.get(col), 0.0) for col in FEATURE_COLUMNS}])
        return _safe_float(model.predict(X)[0])
    except Exception:
        return None


def apply_latest_calibration(
    symbol: str | None,
    horizon: int,
    ohlcv,
    raw_forecast: Optional[dict],
) -> Optional[dict]:
    if not raw_forecast:
        return raw_forecast
    artifact = load_latest_artifact(symbol, horizon)
    if not artifact:
        return mark_uncalibrated(raw_forecast, "No matching price calibration artifact found.")

    asset_class = artifact.get("asset_class") or infer_asset_class(symbol)
    feature_row = build_feature_row(
        ohlcv,
        raw_forecast,
        symbol=symbol,
        asset_class=asset_class,
    )
    residual_model = _load_pickle(artifact.get("residual_model_path"))
    q_models = {
        key: _load_pickle(path)
        for key, path in (artifact.get("quantile_model_paths") or {}).items()
    }
    last = _safe_float(raw_forecast.get("last_close"))
    if not last:
        last = _last_close(ohlcv)
    raw_return = _raw_expected_return(raw_forecast, last)
    residual = predict_model(residual_model, feature_row)
    if residual is None:
        residual = _safe_float(artifact.get("bias"), 0.0) or 0.0
    calibrated_return = raw_return + residual

    q10 = predict_model(q_models.get("q10"), feature_row)
    q50 = predict_model(q_models.get("q50"), feature_row)
    q90 = predict_model(q_models.get("q90"), feature_row)
    residual_q10 = _safe_float(artifact.get("residual_q10"), -0.02) or -0.02
    residual_q90 = _safe_float(artifact.get("residual_q90"), 0.02) or 0.02
    if q10 is None:
        q10 = calibrated_return + residual_q10
    if q50 is None:
        q50 = calibrated_return
    if q90 is None:
        q90 = calibrated_return + residual_q90
    padding = max(0.0, _safe_float(artifact.get("conformal_padding"), 0.0) or 0.0)
    low_ret = min(q10, calibrated_return, q90) - padding
    high_ret = max(q10, calibrated_return, q90) + padding
    p50_ret = _finite(calibrated_return, q50)
    predicted_price = last * (1.0 + p50_ret)
    p10 = last * (1.0 + low_ret)
    p90 = last * (1.0 + high_ret)
    p_up = _prob_from_return(p50_ret, high_ret - low_ret)

    out = dict(raw_forecast)
    out.update({
        "raw_predicted_price": raw_forecast.get("raw_predicted_price", raw_forecast.get("predicted_price")),
        "raw_p10": raw_forecast.get("raw_p10", raw_forecast.get("p10")),
        "raw_p50": raw_forecast.get("raw_p50", raw_forecast.get("p50")),
        "raw_p90": raw_forecast.get("raw_p90", raw_forecast.get("p90")),
        "raw_expected_return": raw_return,
        "foundation_mode": raw_forecast.get("foundation_mode", raw_forecast.get("mode")),
        "predicted_price": round(float(predicted_price), 4),
        "p10": round(float(min(p10, p90)), 4),
        "p50": round(float(predicted_price), 4),
        "p90": round(float(max(p10, p90)), 4),
        "p_up": round(float(p_up), 6),
        "expected_return": round(float(p50_ret), 8),
        "mode": MODEL_VERSION,
        "forecast_kind": "model",
        "is_model_forecast": bool(raw_forecast.get("is_model_forecast", True)),
        "calibration_applied": True,
        "calibration_model_version": artifact.get("model_version") or MODEL_VERSION,
        "calibration_source_run_id": artifact.get("run_id"),
        "calibrated_at": artifact.get("created_at"),
        "calibration_metrics": artifact.get("metrics") or {},
    })
    return out


def mark_uncalibrated(raw_forecast: Optional[dict], reason: str) -> Optional[dict]:
    if not raw_forecast:
        return raw_forecast
    out = dict(raw_forecast)
    out.setdefault("raw_predicted_price", out.get("predicted_price"))
    out.setdefault("raw_p10", out.get("p10"))
    out.setdefault("raw_p50", out.get("p50"))
    out.setdefault("raw_p90", out.get("p90"))
    out["calibration_applied"] = False
    out["calibration_warning"] = reason
    warning = out.get("warning")
    if warning:
        out["warning"] = f"{warning}; {reason}"
    else:
        out["warning"] = reason
    return out


def save_calibration_artifact(
    *,
    symbol: str,
    asset_class: str,
    horizon: int,
    run_id: str,
    samples,
    feature_columns: list[str] | None = None,
) -> Optional[dict]:
    import numpy as np
    import pandas as pd

    feature_columns = feature_columns or FEATURE_COLUMNS
    df = samples.copy() if hasattr(samples, "copy") else pd.DataFrame(samples or [])
    if df.empty or "actual_return" not in df:
        return None
    valid = df.dropna(subset=["actual_return", "raw_expected_return"]).copy()
    if valid.empty:
        return None
    valid["residual"] = valid["actual_return"].astype(float) - valid["raw_expected_return"].astype(float)
    X = valid[feature_columns].fillna(0.0)
    residual_model = train_residual_model(X, valid["residual"]) if len(valid) >= 20 else None
    q_models = {}
    if len(valid) >= 20:
        for key, alpha in (("q10", 0.10), ("q50", 0.50), ("q90", 0.90)):
            q_models[key] = train_quantile_model(X, valid["actual_return"], alpha)

    out_dir = artifact_dir(symbol, horizon)
    out_dir.mkdir(parents=True, exist_ok=True)
    residual_path = out_dir / f"{run_id}_residual.pkl"
    quantile_paths = {
        key: out_dir / f"{run_id}_{key}.pkl"
        for key in ("q10", "q50", "q90")
    }
    saved_quantiles = {}
    if residual_model is not None:
        _dump_pickle(residual_model, residual_path)
    for key, model in q_models.items():
        if model is not None:
            _dump_pickle(model, quantile_paths[key])
            saved_quantiles[key] = str(quantile_paths[key])

    scores = []
    if {"calibrated_p10", "calibrated_p90", "actual_return"}.issubset(valid.columns):
        for _idx, row in valid.iterrows():
            low = _safe_float(row.get("calibrated_p10"))
            high = _safe_float(row.get("calibrated_p90"))
            last = _safe_float(row.get("last_close"))
            actual_ret = _safe_float(row.get("actual_return"))
            if low is None or high is None or not last or actual_ret is None:
                continue
            low_ret = low / last - 1.0
            high_ret = high / last - 1.0
            scores.append(max(low_ret - actual_ret, actual_ret - high_ret, 0.0))

    artifact = {
        "model_version": MODEL_VERSION,
        "symbol": canonical_symbol(symbol),
        "asset_class": asset_class,
        "horizon": int(horizon),
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "feature_columns": feature_columns,
        "bias": _finite(valid["residual"].median(), 0.0),
        "residual_q10": _finite(valid["residual"].quantile(0.10), -0.02),
        "residual_q90": _finite(valid["residual"].quantile(0.90), 0.02),
        "conformal_padding": _finite(np.quantile(scores, 0.80), 0.0) if scores else 0.0,
        "residual_model_path": str(residual_path) if residual_model is not None else None,
        "quantile_model_paths": saved_quantiles,
        "metrics": _calibration_metrics(valid),
    }
    (out_dir / "latest.json").write_text(json.dumps(artifact, indent=2, default=str), encoding="utf-8")
    return artifact


def _train_regressor(X, y, *, kind: str, alpha: float = 0.5):
    try:
        import lightgbm as lgb

        params = {
            "n_estimators": 90,
            "learning_rate": 0.04,
            "max_depth": -1,
            "num_leaves": 15,
            "min_data_in_leaf": max(5, min(30, len(X) // 8 or 5)),
            "verbose": -1,
            "random_state": 7,
        }
        if kind == "quantile":
            params.update({"objective": "quantile", "alpha": alpha})
        else:
            params.update({"objective": "regression"})
        model = lgb.LGBMRegressor(**params)
        model.fit(X.fillna(0.0), y.astype(float))
        return model
    except Exception:
        try:
            from sklearn.ensemble import GradientBoostingRegressor

            if kind == "quantile":
                model = GradientBoostingRegressor(
                    loss="quantile",
                    alpha=alpha,
                    n_estimators=80,
                    max_depth=2,
                    learning_rate=0.05,
                    random_state=7,
                )
            else:
                model = GradientBoostingRegressor(
                    n_estimators=80,
                    max_depth=2,
                    learning_rate=0.05,
                    random_state=7,
                )
            model.fit(X.fillna(0.0), y.astype(float))
            return model
        except Exception:
            return None


def _calibration_metrics(df) -> dict:
    import numpy as np

    actual_price = df.get("actual_price")
    cal_price = df.get("calibrated_predicted_price")
    raw_price = df.get("raw_predicted_price")
    actual_return = df.get("actual_return").astype(float)
    cal_return = df.get("calibrated_expected_return")
    if cal_return is None:
        cal_return = df.get("raw_expected_return").astype(float) + float(df["residual"].median())
    cal_error_ret = actual_return - cal_return.astype(float)
    raw_error_ret = actual_return - df.get("raw_expected_return").astype(float)
    out = {
        "calibration_sample_count": int(len(df)),
        "bias": _finite(df["residual"].median(), 0.0),
        "mae_return": _finite(cal_error_ret.abs().mean(), 0.0),
        "rmse_return": _finite(math.sqrt(float((cal_error_ret ** 2).mean())), 0.0),
        "raw_mae_return": _finite(raw_error_ret.abs().mean(), 0.0),
        "raw_rmse_return": _finite(math.sqrt(float((raw_error_ret ** 2).mean())), 0.0),
    }
    if actual_price is not None and cal_price is not None:
        price_err = actual_price.astype(float) - cal_price.astype(float)
        out["mae"] = _finite(price_err.abs().mean(), 0.0)
        out["rmse"] = _finite(math.sqrt(float((price_err ** 2).mean())), 0.0)
        out["mape"] = _finite((price_err.abs() / actual_price.astype(float).abs().replace(0, np.nan)).mean(), 0.0)
    if actual_price is not None and raw_price is not None:
        raw_price_err = actual_price.astype(float) - raw_price.astype(float)
        out["raw_mae"] = _finite(raw_price_err.abs().mean(), 0.0)
        out["raw_rmse"] = _finite(math.sqrt(float((raw_price_err ** 2).mean())), 0.0)
    if {"calibrated_p10", "calibrated_p90", "actual_price"}.issubset(df.columns):
        low = df["calibrated_p10"].astype(float)
        high = df["calibrated_p90"].astype(float)
        actual = df["actual_price"].astype(float)
        out["coverage_80"] = _finite(((actual >= low) & (actual <= high)).mean(), 0.0)
        out["avg_interval_width"] = _finite(((high - low) / actual.abs().replace(0, np.nan)).mean(), 0.0)
    return out


def _dump_pickle(model: Any, path: Path) -> None:
    with path.open("wb") as fh:
        pickle.dump(model, fh)


def _load_pickle(path: Any) -> Any:
    if not path:
        return None
    try:
        fp = Path(str(path))
        if not fp.exists():
            return None
        with fp.open("rb") as fh:
            return pickle.load(fh)
    except Exception:
        return None


def _raw_expected_return(raw_forecast: dict, last_close: float) -> float:
    value = _safe_float(raw_forecast.get("expected_return"))
    if value is not None:
        return value
    pred = _safe_float(raw_forecast.get("predicted_price"), last_close)
    return pred / max(abs(last_close), 1e-9) - 1.0


def _last_close(ohlcv) -> float:
    try:
        return float(ohlcv["close"].astype(float).dropna().iloc[-1])
    except Exception:
        return 0.0


def _period_return(close, periods: int) -> float:
    if len(close) <= periods:
        return 0.0
    prev = float(close.iloc[-periods - 1])
    return float(close.iloc[-1]) / prev - 1.0 if prev else 0.0


def _rolling_std(ret, window: int) -> float:
    s = ret.tail(window).dropna()
    return float(s.std(ddof=0)) if len(s) else 0.0


def _volume_z(volume, window: int) -> float:
    if volume is None or len(volume.dropna()) < 5:
        return 0.0
    s = volume.tail(window).dropna().astype(float)
    sd = float(s.std(ddof=0))
    if not sd:
        return 0.0
    return max(-5.0, min(5.0, (float(s.iloc[-1]) - float(s.mean())) / sd))


def _drawdown(close, window: int) -> float:
    if close.empty:
        return 0.0
    s = close.tail(window).astype(float)
    peak = float(s.max()) if len(s) else 0.0
    last = float(s.iloc[-1]) if len(s) else 0.0
    return last / peak - 1.0 if peak else 0.0


def _rsi(close, window: int) -> float:
    if len(close) < window + 1:
        return 50.0
    delta = close.diff().tail(window).dropna()
    gain = delta[delta > 0].mean() if len(delta[delta > 0]) else 0.0
    loss = -delta[delta < 0].mean() if len(delta[delta < 0]) else 0.0
    if not loss:
        return 100.0 if gain else 50.0
    rs = gain / loss
    return float(100.0 - (100.0 / (1.0 + rs)))


def _macd(close) -> tuple[float, float, float]:
    if len(close) < 3:
        return 0.0, 0.0, 0.0
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return float(macd.iloc[-1]), float(signal.iloc[-1]), float((macd - signal).iloc[-1])


def _prob_from_return(expected_return: float, width: float) -> float:
    scale = max(abs(width) / 2.0, 0.01)
    return max(0.01, min(0.99, 0.5 + 0.42 * math.tanh(expected_return / scale)))


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _finite(value: Any, default: float = 0.0) -> float:
    number = _safe_float(value)
    return float(default if number is None else number)


def _get(row: Any, key: str) -> Any:
    if row is None:
        return None
    try:
        return row.get(key)
    except AttributeError:
        try:
            return row[key]
        except Exception:
            return None
