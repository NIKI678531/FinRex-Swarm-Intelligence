"""Walk-forward ML calibration for foundation price-point forecasts."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Optional

from .. import config
from ..features.swarm_factors import SWARM_FACTORS, compute_swarm_factors
from ..models.price_point_calibrator import (
    FEATURE_COLUMNS,
    MODEL_VERSION,
    build_feature_row,
    canonical_symbol,
    foundation_or_fallback_forecast,
    infer_asset_class,
    predict_model,
    save_calibration_artifact,
    train_quantile_model,
    train_residual_model,
)
from . import performance as perf


@dataclass
class PricePointCalibratedMLBacktestResult:
    signals: object
    perf_market: dict
    perf_swarm: dict
    perf_hybrid: dict
    ic: dict
    data_quality: dict


def run_price_point_calibrated_ml_backtest(
    ohlcv,
    symbol: str,
    horizon: int = 5,
    swarm_source_mode: str = "auto",
    oasis_simulation_id: Optional[str] = None,
    sentiment_sources: Optional[list[str]] = None,
    train_days: Optional[int] = None,
    step_days: Optional[int] = None,
    run_id: Optional[str] = None,
) -> PricePointCalibratedMLBacktestResult:
    """Run no-lookahead price-point calibration.

    At each bar the raw foundation forecast is produced from history only.
    The residual and quantile calibrators are trained only on earlier forecasts
    whose horizon outcome has already resolved.
    """
    import pandas as pd

    horizon = max(1, int(horizon or 1))
    symbol = canonical_symbol(symbol)
    asset_class = infer_asset_class(symbol)
    train_days = train_days or config.WF_TRAIN_DAYS
    step_days = step_days or config.WF_STEP_DAYS
    min_ml_samples = max(30, min(90, int(train_days) // 6))
    retrain_every = max(10, int(getattr(config, "PRICE_ML_RETRAIN_EVERY", 60) or 60))

    close = ohlcv["close"].astype(float)
    fwd_ret = close.shift(-horizon) / close - 1.0
    fwd_price = close.shift(-horizon)
    daily_ret = close.pct_change().shift(-1)

    swarm = _safe_swarm(
        symbol,
        ohlcv.index.min(),
        ohlcv.index.max(),
        source_mode=swarm_source_mode,
        oasis_simulation_id=oasis_simulation_id,
        sentiment_sources=sentiment_sources,
    )
    swarm_quality = dict(swarm.attrs.get("data_quality") or {})
    swarm = swarm.reindex(ohlcv.index).ffill(limit=config.SWARM_FFILL_LIMIT)
    swarm_quality["effective_rows"] = int((~swarm.isna().all(axis=1)).sum()) if len(swarm) else 0
    swarm_quality["coverage_ratio"] = (
        swarm_quality["effective_rows"] / len(swarm) if len(swarm) else 0.0
    )

    warmup = min(max(90, horizon * 20), max(32, len(ohlcv) // 3))
    end_pos = max(warmup, len(ohlcv) - horizon)
    history: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    idx: list[Any] = []
    state = _RollingMLState(min_samples=min_ml_samples, retrain_every=retrain_every)
    fallback_reasons: set[str] = set()
    foundation_modes: set[str] = set()

    all_positions = list(range(warmup, end_pos))
    max_backtest_bars = int(getattr(config, "PRICE_ML_MAX_BACKTEST_BARS", 420) or 0)
    positions = all_positions[-max_backtest_bars:] if max_backtest_bars > 0 else all_positions
    foundation_positions, foundation_policy = _select_foundation_positions(positions)
    foundation_calls = 0
    numerical_fallback_calls = 0

    for pos in positions:
        hist = ohlcv.iloc[:pos + 1]
        use_foundation = pos in foundation_positions
        if use_foundation:
            foundation_calls += 1
        else:
            numerical_fallback_calls += 1
        raw, fallback_reason = foundation_or_fallback_forecast(
            hist,
            horizon=horizon,
            use_foundation=use_foundation,
            skip_reason=f"Foundation inference skipped by {foundation_policy} backtest policy.",
        )
        if fallback_reason:
            fallback_reasons.add(str(fallback_reason))
        foundation_modes.add(str(raw.get("mode") or "unknown"))
        swarm_row = swarm.iloc[pos] if pos < len(swarm) else None
        feature_row = build_feature_row(
            hist,
            raw,
            symbol=symbol,
            asset_class=asset_class,
            swarm_row=swarm_row,
        )

        available = [item for item in history if int(item["resolved_pos"]) <= pos]
        state.fit_if_due(available)
        calibrated = _calibrate_one(
            raw=raw,
            feature_row=feature_row,
            available=available,
            state=state,
            last_close=float(close.iloc[pos]),
        )

        actual_return = _num(fwd_ret.iloc[pos])
        actual_px = _num(fwd_price.iloc[pos])
        ts = ohlcv.index[pos]
        row = {
            "p_market": _num(raw.get("p_up"), 0.5),
            "p_swarm": _swarm_probability(swarm_row),
            "p_meta": calibrated["p_up"],
            "signal_market": _signal_from_return(calibrated["raw_expected_return"]),
            "signal_swarm": _signal_from_prob(_swarm_probability(swarm_row)),
            "signal_hybrid": _signal_from_return(calibrated["calibrated_expected_return"]),
            "ret_next": _num(daily_ret.iloc[pos]),
            "last_close": float(close.iloc[pos]),
            "raw_predicted_price": _num(raw.get("predicted_price")),
            "raw_p10": _num(raw.get("p10")),
            "raw_p50": _num(raw.get("p50", raw.get("predicted_price"))),
            "raw_p90": _num(raw.get("p90")),
            "raw_expected_return": calibrated["raw_expected_return"],
            "calibrated_predicted_price": calibrated["predicted_price"],
            "calibrated_p10": calibrated["p10"],
            "calibrated_p50": calibrated["predicted_price"],
            "calibrated_p90": calibrated["p90"],
            "calibrated_expected_return": calibrated["calibrated_expected_return"],
            "predicted_price": calibrated["predicted_price"],
            "p10": calibrated["p10"],
            "p50": calibrated["predicted_price"],
            "p90": calibrated["p90"],
            "actual_return": actual_return,
            "actual_price": actual_px,
            "price_error": None if actual_px is None else actual_px - calibrated["predicted_price"],
            "raw_price_error": None if actual_px is None or raw.get("predicted_price") is None else actual_px - float(raw["predicted_price"]),
            "interval_hit": None if actual_px is None else bool(calibrated["p10"] <= actual_px <= calibrated["p90"]),
            "calibration_sample_count": len(available),
            "calibration_mode": calibrated["mode"],
            "foundation_mode": raw.get("mode"),
            "foundation_uncertainty": _num(raw.get("foundation_uncertainty", raw.get("uncertainty"))),
            "cross_model_agreement": _num(raw.get("cross_model_agreement")),
            "vol_5d": feature_row["vol_5"],
            "vol_20d": feature_row["vol_20"],
            "volume_z": feature_row["volume_z_20"],
            "event_flag": _num(_get(swarm_row, "event_intensity"), 0.0),
        }
        for col in FEATURE_COLUMNS:
            row[col] = feature_row[col]
        rows.append(row)
        idx.append(ts)

        if actual_return is not None:
            history.append({
                **{col: feature_row[col] for col in FEATURE_COLUMNS},
                "resolved_pos": pos + horizon,
                "actual_return": actual_return,
                "actual_price": actual_px,
                "last_close": float(close.iloc[pos]),
                "raw_expected_return": calibrated["raw_expected_return"],
                "raw_predicted_price": _num(raw.get("predicted_price")),
                "calibrated_expected_return": calibrated["calibrated_expected_return"],
                "calibrated_predicted_price": calibrated["predicted_price"],
                "calibrated_p10": calibrated["p10"],
                "calibrated_p90": calibrated["p90"],
            })

    if rows:
        signals = pd.DataFrame(rows, index=pd.DatetimeIndex(idx))
    else:
        signals = pd.DataFrame(columns=[
            "p_market", "p_swarm", "p_meta", "signal_market",
            "signal_swarm", "signal_hybrid", "ret_next",
        ], index=ohlcv.index[:0])

    perf_m = perf.compute_performance(signals["signal_market"] * signals["ret_next"], benchmark_returns=signals["ret_next"])
    perf_s = perf.compute_performance(signals["signal_swarm"] * signals["ret_next"], benchmark_returns=signals["ret_next"])
    perf_h = perf.compute_performance(signals["signal_hybrid"] * signals["ret_next"], benchmark_returns=signals["ret_next"])
    ic = perf.compute_ic(signals["calibrated_expected_return"] if "calibrated_expected_return" in signals else signals["p_meta"], fwd_ret.reindex(signals.index))

    artifact = None
    if run_id and len(signals):
        artifact = save_calibration_artifact(
            symbol=symbol,
            asset_class=asset_class,
            horizon=horizon,
            run_id=run_id,
            samples=signals.dropna(subset=["actual_return"]),
            feature_columns=FEATURE_COLUMNS,
        )

    price_quality = _price_quality(
        signals,
        horizon=horizon,
        warmup=warmup,
        min_ml_samples=min_ml_samples,
        retrain_every=retrain_every,
        asset_class=asset_class,
        foundation_modes=foundation_modes,
        fallback_reasons=fallback_reasons,
        artifact=artifact,
        total_candidate_bars=len(all_positions),
        emitted_bars=len(positions),
        max_backtest_bars=max_backtest_bars,
        foundation_policy=foundation_policy,
        foundation_call_limit=config.PRICE_ML_MAX_FOUNDATION_CALLS,
        foundation_calls=foundation_calls,
        numerical_fallback_calls=numerical_fallback_calls,
    )

    return PricePointCalibratedMLBacktestResult(
        signals=signals,
        perf_market=perf_m,
        perf_swarm=perf_s,
        perf_hybrid=perf_h,
        ic=ic,
        data_quality={
            "swarm": _finalize_swarm_quality(swarm_quality, signals),
            "price_forecast_model": price_quality,
        },
    )


class _RollingMLState:
    def __init__(self, *, min_samples: int, retrain_every: int):
        self.min_samples = int(min_samples)
        self.retrain_every = int(retrain_every)
        self.last_train_n = 0
        self.residual_model = None
        self.quantile_models: dict[str, Any] = {}

    def fit_if_due(self, available: list[dict[str, Any]]) -> None:
        if len(available) < self.min_samples:
            return
        if self.residual_model is not None and len(available) - self.last_train_n < self.retrain_every:
            return
        import pandas as pd

        df = pd.DataFrame(available).dropna(subset=["actual_return", "raw_expected_return"])
        if len(df) < self.min_samples:
            return
        X = df[FEATURE_COLUMNS].fillna(0.0)
        residual = df["actual_return"].astype(float) - df["raw_expected_return"].astype(float)
        self.residual_model = train_residual_model(X, residual)
        self.quantile_models = {
            "q10": train_quantile_model(X, df["actual_return"], 0.10),
            "q50": train_quantile_model(X, df["actual_return"], 0.50),
            "q90": train_quantile_model(X, df["actual_return"], 0.90),
        }
        self.last_train_n = len(df)


def _select_foundation_positions(positions: list[int]) -> tuple[set[int], str]:
    if not positions:
        return set(), "none"
    mode = str(getattr(config, "PRICE_ML_FOUNDATION_MODE", "none") or "none").strip().lower()
    max_calls = max(0, int(getattr(config, "PRICE_ML_MAX_FOUNDATION_CALLS", 1) or 0))
    if mode in {"none", "off", "disabled", "0"} or max_calls <= 0:
        return set(), mode or "none"
    if mode == "full":
        return set(positions), "full"
    if mode in {"tail", "recent", "latest"}:
        n = 1 if mode == "latest" else min(max_calls, len(positions))
        return set(positions[-n:]), mode
    if mode in {"sample", "sampled", "even"}:
        n = min(max_calls, len(positions))
        if n <= 1:
            return {positions[-1]}, mode
        step = (len(positions) - 1) / float(n - 1)
        return {positions[round(i * step)] for i in range(n)}, mode
    return set(), f"unknown:{mode}"


def _calibrate_one(raw: dict, feature_row: dict, available: list[dict[str, Any]], state: _RollingMLState, last_close: float) -> dict:
    import numpy as np
    import pandas as pd

    raw_expected = _raw_expected_return(raw, last_close)
    residuals = []
    if available:
        df = pd.DataFrame(available)
        residuals = (df["actual_return"].astype(float) - df["raw_expected_return"].astype(float)).dropna().tolist()
    bias = float(np.median(residuals)) if residuals else 0.0
    residual_pred = predict_model(state.residual_model, feature_row)
    if residual_pred is None:
        residual_pred = bias
    calibrated_return = raw_expected + float(residual_pred)

    q10 = predict_model(state.quantile_models.get("q10"), feature_row)
    q50 = predict_model(state.quantile_models.get("q50"), feature_row)
    q90 = predict_model(state.quantile_models.get("q90"), feature_row)
    if residuals:
        r10 = float(np.quantile(residuals, 0.10))
        r90 = float(np.quantile(residuals, 0.90))
    else:
        width = _num(raw.get("foundation_uncertainty", raw.get("uncertainty")), 0.02)
        r10, r90 = -abs(width), abs(width)
    if q10 is None:
        q10 = calibrated_return + r10
    if q50 is None:
        q50 = calibrated_return
    if q90 is None:
        q90 = calibrated_return + r90
    low_ret = min(float(q10), float(q50), calibrated_return)
    high_ret = max(float(q90), float(q50), calibrated_return)
    if high_ret - low_ret < 1e-6:
        pad = max(0.005, abs(calibrated_return) * 0.5)
        low_ret -= pad
        high_ret += pad
    predicted_price = last_close * (1.0 + calibrated_return)
    p10 = last_close * (1.0 + low_ret)
    p90 = last_close * (1.0 + high_ret)
    p_up = _prob_from_return(calibrated_return, high_ret - low_ret)
    mode = "ml_residual_quantile" if state.residual_model is not None else ("rolling_residual_quantile" if residuals else "raw_plus_initial_band")
    return {
        "raw_expected_return": raw_expected,
        "calibrated_expected_return": float(calibrated_return),
        "predicted_price": float(predicted_price),
        "p10": float(min(p10, p90)),
        "p90": float(max(p10, p90)),
        "p_up": float(p_up),
        "mode": mode,
    }


def _safe_swarm(symbol: str, start, end, **kwargs):
    import pandas as pd

    try:
        return compute_swarm_factors(symbol, start, end, **kwargs)
    except Exception as exc:  # noqa: BLE001
        df = pd.DataFrame(columns=SWARM_FACTORS, index=pd.DatetimeIndex([], tz="UTC", name="ts"))
        df.attrs["data_quality"] = {
            "source_mode": kwargs.get("source_mode") or "auto",
            "fallback_reason": f"swarm_unavailable: {exc}",
            "effective_rows": 0,
            "coverage_ratio": 0.0,
        }
        return df


def _price_quality(signals, **kwargs) -> dict:
    import math

    valid = signals.dropna(subset=["actual_return"]) if len(signals) else signals
    artifact = kwargs.get("artifact")
    metrics = (artifact or {}).get("metrics") or {}
    if not metrics and len(valid):
        err = valid["actual_return"].astype(float) - valid["calibrated_expected_return"].astype(float)
        raw_err = valid["actual_return"].astype(float) - valid["raw_expected_return"].astype(float)
        metrics = {
            "calibration_sample_count": int(len(valid)),
            "mae_return": float(err.abs().mean()),
            "rmse_return": math.sqrt(float((err ** 2).mean())),
            "raw_mae_return": float(raw_err.abs().mean()),
            "raw_rmse_return": math.sqrt(float((raw_err ** 2).mean())),
        }
        if "interval_hit" in valid:
            metrics["coverage_80"] = float(valid["interval_hit"].dropna().mean()) if valid["interval_hit"].dropna().size else 0.0
    return {
        "engine": MODEL_VERSION,
        "horizon_days": int(kwargs.get("horizon") or 1),
        "warmup_bars": int(kwargs.get("warmup") or 0),
        "asset_class": kwargs.get("asset_class"),
        "total_candidate_bars": int(kwargs.get("total_candidate_bars") or 0),
        "emitted_bars": int(kwargs.get("emitted_bars") or 0),
        "max_backtest_bars": int(kwargs.get("max_backtest_bars") or 0),
        "min_ml_samples": int(kwargs.get("min_ml_samples") or 0),
        "retrain_every": int(kwargs.get("retrain_every") or 0),
        "foundation_modes": sorted(kwargs.get("foundation_modes") or []),
        "fallback_reasons": sorted(kwargs.get("fallback_reasons") or []),
        "foundation_policy": kwargs.get("foundation_policy") or "none",
        "foundation_call_limit": int(kwargs.get("foundation_call_limit") or 0),
        "foundation_calls": int(kwargs.get("foundation_calls") or 0),
        "numerical_fallback_calls": int(kwargs.get("numerical_fallback_calls") or 0),
        "artifact": artifact,
        **metrics,
    }


def _finalize_swarm_quality(swarm_quality: dict, signals) -> dict:
    p_swarm = signals.get("p_swarm") if signals is not None and len(signals) else None
    signal_swarm = signals.get("signal_swarm") if signals is not None and len(signals) else None
    p_unique = int(p_swarm.nunique(dropna=True)) if p_swarm is not None else 0
    signal_unique = int(signal_swarm.nunique(dropna=True)) if signal_swarm is not None else 0
    signal_abs_sum = float(signal_swarm.fillna(0.0).abs().sum()) if signal_swarm is not None else 0.0
    constant_warning = p_unique <= 1 or signal_unique <= 1 or signal_abs_sum == 0.0
    return {
        **(swarm_quality or {}),
        "p_swarm_unique": p_unique,
        "signal_swarm_unique": signal_unique,
        "constant_signal_warning": bool(constant_warning),
    }


def _swarm_probability(row: Any) -> float:
    sentiment = _num(_get(row, "sentiment_mean"), 0.0)
    bull = _num(_get(row, "bull_ratio"), 0.0)
    pulse = _num(_get(row, "event_intensity"), 0.0)
    score = math.tanh(0.55 * sentiment + 0.25 * bull + 0.20 * pulse)
    return max(0.05, min(0.95, 0.5 + 0.32 * score))


def _signal_from_prob(p: float) -> float:
    return max(-1.0, min(1.0, (float(p) - 0.5) * 2.0))


def _signal_from_return(value: float) -> float:
    return max(-1.0, min(1.0, math.tanh(float(value or 0.0) / 0.03)))


def _raw_expected_return(raw: dict, last_close: float) -> float:
    value = _num(raw.get("expected_return"))
    if value is not None:
        return float(value)
    pred = _num(raw.get("predicted_price"), last_close)
    return float(pred) / max(abs(last_close), 1e-9) - 1.0


def _prob_from_return(expected_return: float, width: float) -> float:
    scale = max(abs(width) / 2.0, 0.01)
    return max(0.01, min(0.99, 0.5 + 0.42 * math.tanh(expected_return / scale)))


def _num(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
    except (TypeError, ValueError):
        return default


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
