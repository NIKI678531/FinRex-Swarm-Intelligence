"""End-to-end orchestration: fetch data, features, train, backtest, persist."""

from __future__ import annotations

import json
import logging
import math
import time
import uuid

from . import config
from .data import market_data
from .backtest.financial_forecast import run_financial_forecast_backtest
from .backtest.price_point_calibrated_ml import run_price_point_calibrated_ml_backtest
from .backtest.walk_forward import run_walk_forward
from .backtest.vectorbt_runner import simulate

logger = logging.getLogger(__name__)


def run_backtest(
    symbol: str,
    start,
    end,
    horizon: int = None,
    initial_cash: float = 10000.0,
    swarm_source_mode: str = "auto",
    oasis_simulation_id: str | None = None,
    sentiment_sources: list[str] | None = None,
    fee_bps: float = 5.0,
    exposure: float = 0.95,
    allow_short: bool = True,
    signal_threshold: float = 0.0,
    train_days: int | None = None,
    test_days: int | None = None,
    step_days: int | None = None,
    model_family: str = "price_point_calibrated_ml",
) -> dict:
    """Top-level entry. Returns a dict suitable for JSON serialization.

    Side-effect: persists results into ``config.BACKTEST_RUNS_DIR/<run_id>``.
    """
    horizon = horizon or config.PREDICT_HORIZON_DAYS
    config.ensure_dirs()
    run_id = f"run_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    run_dir = config.BACKTEST_RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    ohlcv = market_data.fetch_ohlcv(symbol, start, end)
    market_quality = dict(ohlcv.attrs.get("data_quality") or {})
    min_bars = max(60, int(horizon) * 12)
    if len(ohlcv) < min_bars:
        source = market_quality.get("data_source") or "unknown"
        raise RuntimeError(
            f"Not enough OHLCV data for {symbol}: fetched {len(ohlcv)} daily bars from {source}, "
            f"need at least {min_bars}. Please extend the date range."
        )
    model_family = _normalize_model_family(model_family)
    if model_family == "two_tower":
        result = run_walk_forward(
            ohlcv,
            symbol=symbol,
            horizon=horizon,
            train_days=train_days,
            test_days=test_days,
            step_days=step_days,
            swarm_source_mode=swarm_source_mode,
            oasis_simulation_id=oasis_simulation_id,
            sentiment_sources=sentiment_sources,
        )
    elif model_family == "price_point_calibrated_ml":
        result = run_price_point_calibrated_ml_backtest(
            ohlcv,
            symbol=symbol,
            horizon=horizon,
            train_days=train_days,
            step_days=step_days,
            swarm_source_mode=swarm_source_mode,
            oasis_simulation_id=oasis_simulation_id,
            sentiment_sources=sentiment_sources,
            run_id=run_id,
        )
    else:
        result = run_financial_forecast_backtest(
            ohlcv,
            symbol=symbol,
            horizon=horizon,
            swarm_source_mode=swarm_source_mode,
            oasis_simulation_id=oasis_simulation_id,
            sentiment_sources=sentiment_sources,
        )

    sig = result.signals
    sim = simulate(
        ohlcv["close"].reindex(sig.index),
        sig["signal_hybrid"],
        initial_cash=initial_cash,
        fee_bps=fee_bps,
        exposure=exposure,
        allow_short=allow_short,
        signal_threshold=signal_threshold,
    )
    chart_points = _build_chart_points(ohlcv, sig, sim["equity_curve"])
    trade_log = _enrich_trade_log(sim.get("trade_log", []), sig)
    data_quality = dict(result.data_quality or {})
    data_quality["market"] = market_quality

    payload = {
        "run_id": run_id,
        "symbol": symbol,
        "start": str(start),
        "end": str(end),
        "horizon": horizon,
        "config": {
            "model_family": model_family,
            "swarm_source_mode": swarm_source_mode,
            "oasis_simulation_id": oasis_simulation_id,
            "sentiment_sources": sentiment_sources or ["fmp"],
            "fee_bps": fee_bps,
            "exposure": exposure,
            "allow_short": allow_short,
            "signal_threshold": signal_threshold,
            "train_days": train_days,
            "test_days": test_days,
            "step_days": step_days,
        },
        "performance": {
            "market_only": result.perf_market,
            "swarm_only": result.perf_swarm,
            "hybrid": result.perf_hybrid,
            "ic": result.ic,
        },
        "data_quality": data_quality,
        "equity_curve": sim["equity_curve"],
        "trades": sim["trades"],
        "trade_log": trade_log,
        "summary": sim["summary"],
        "chart_points": chart_points,
        "pro_series": _build_pro_series(sim["equity_curve"]),
        "pro_distributions": _build_pro_distributions(trade_log),
    }

    (run_dir / "result.json").write_text(json.dumps(payload, default=str), encoding="utf-8")
    try:
        sig.reset_index().to_parquet(run_dir / "signals.parquet")
    except Exception as exc:  # noqa: BLE001
        logger.warning("signals parquet write failed: %s", exc)
    return payload


def get_run(run_id: str) -> dict:
    run_dir = config.BACKTEST_RUNS_DIR / run_id
    fp = run_dir / "result.json"
    if not fp.exists():
        raise FileNotFoundError(run_id)
    return json.loads(fp.read_text(encoding="utf-8"))


def list_runs() -> "list[dict]":
    config.ensure_dirs()
    out = []
    for d in sorted(config.BACKTEST_RUNS_DIR.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        fp = d / "result.json"
        if not fp.exists():
            continue
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            out.append({
                "run_id": data["run_id"],
                "symbol": data["symbol"],
                "start": data["start"],
                "end": data["end"],
                "model_family": (data.get("config") or {}).get("model_family"),
                "summary": data.get("summary", {}),
                "data_quality": data.get("data_quality", {}),
            })
        except Exception:
            continue
    return out


def latest_signal(symbol: str) -> dict:
    """Return the newest persisted Quant signal for paper-trading consumers."""
    config.ensure_dirs()
    for d in sorted(config.BACKTEST_RUNS_DIR.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        fp = d / "result.json"
        if not fp.exists():
            continue
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("symbol") != symbol:
            continue
        out = {
            "symbol": symbol,
            "run_id": data.get("run_id"),
            "data_quality": data.get("data_quality", {}),
            "signal_hybrid": None,
            "signal_swarm": None,
            "p_meta": None,
            "p_swarm": None,
            "predicted_price": None,
            "predicted_band_low": None,
            "predicted_band_high": None,
            "last_close": None,
            "as_of": None,
            "ts": None,
        }
        sig_fp = d / "signals.parquet"
        if sig_fp.exists():
            try:
                import pandas as pd

                sig = pd.read_parquet(sig_fp)
                row = sig.iloc[-1]
                out.update({
                    "ts": str(row.get("ts") or row.name),
                    "signal_hybrid": _num(row.get("signal_hybrid")),
                    "signal_swarm": _num(row.get("signal_swarm")),
                    "p_meta": _num(row.get("p_meta")),
                    "p_swarm": _num(row.get("p_swarm")),
                    "predicted_price": _num(row.get("predicted_price")),
                    "predicted_band_low": _num(row.get("p10")),
                    "predicted_band_high": _num(row.get("p90")),
                    "last_close": _num(row.get("last_close")),
                    "as_of": str(row.get("ts") or row.name),
                })
                return out
            except Exception as exc:  # noqa: BLE001
                logger.warning("latest signal parquet read failed: %s", exc)
        points = data.get("chart_points") or []
        if points:
            row = points[-1]
            out.update({
                "ts": row.get("ts"),
                "signal_hybrid": _num(row.get("signal_hybrid")),
                "p_meta": _num(row.get("p_meta")),
                "predicted_price": _num(row.get("predicted_price")),
                "predicted_band_low": _num(row.get("p10")),
                "predicted_band_high": _num(row.get("p90")),
                "last_close": _num(row.get("close")),
                "as_of": row.get("ts"),
            })
        return out
    raise FileNotFoundError(symbol)


def delete_run(run_id: str) -> bool:
    import shutil

    run_dir = config.BACKTEST_RUNS_DIR / run_id
    if not run_dir.exists():
        return False
    shutil.rmtree(run_dir, ignore_errors=True)
    return True


def _normalize_model_family(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"two_tower", "dual_tower", "hybrid_alpha", "market_swarm", "legacy"}:
        return "two_tower"
    if raw in {
        "price_point_calibrated_ml",
        "price_point_ml",
        "calibrated_ml",
        "calibrated_price_ml",
        "price_point_calibrated",
        "price_forecast_ml",
        "price_forecast",
        "forecast",
        "",
    }:
        return "price_point_calibrated_ml"
    if raw in {"financial_forecast", "financial_sentiment"}:
        return "financial_forecast"
    raise ValueError("model_family must be price_point_calibrated_ml, financial_forecast, or two_tower")


def _build_chart_points(ohlcv, signals, equity_curve: list[dict]) -> list[dict]:
    """Build UI-ready rows with OHLCV, broker state, model signal, and indicators."""
    import pandas as pd

    if signals is None or len(signals) == 0:
        return []

    idx = pd.DatetimeIndex(signals.index)
    market = ohlcv.reindex(idx)
    indicators = _technical_indicators(ohlcv).reindex(idx)

    broker = pd.DataFrame(equity_curve or [])
    if not broker.empty and "ts" in broker.columns:
        broker["_idx"] = pd.to_datetime(broker["ts"], utc=True)
        broker = broker.set_index("_idx").reindex(idx)
    else:
        broker = pd.DataFrame(index=idx)

    rows = []
    for pos, ts in enumerate(idx):
        m = market.iloc[pos]
        s = signals.iloc[pos]
        ind = indicators.iloc[pos]
        b = broker.iloc[pos] if len(broker) else {}
        rows.append({
            "ts": ts.isoformat(),
            "open": _num(m.get("open")),
            "high": _num(m.get("high")),
            "low": _num(m.get("low")),
            "close": _num(m.get("close")),
            "volume": _num(m.get("volume")),
            "cash": _num(_get(b, "cash")),
            "value": _num(_get(b, "value")),
            "position_side": _text(_get(b, "position_side"), "flat"),
            "position_units": _num(_get(b, "position_units")),
            "p_meta": _num(s.get("p_meta")),
            "signal_hybrid": _num(s.get("signal_hybrid")),
            "predicted_price": _num(s.get("predicted_price")),
            "p10": _num(s.get("p10")),
            "p50": _num(s.get("p50")),
            "p90": _num(s.get("p90")),
            "raw_predicted_price": _num(s.get("raw_predicted_price")),
            "calibrated_expected_return": _num(s.get("calibrated_expected_return")),
            "calibration_sample_count": _num(s.get("calibration_sample_count")),
            "ema_9": _num(ind.get("ema_9")),
            "ema_12": _num(ind.get("ema_12")),
            "ema_26": _num(ind.get("ema_26")),
            "kdj_k": _num(ind.get("kdj_k")),
            "kdj_d": _num(ind.get("kdj_d")),
            "kdj_j": _num(ind.get("kdj_j")),
            "highest_9": _num(ind.get("highest_9")),
            "lowest_9": _num(ind.get("lowest_9")),
            "macd": _num(ind.get("macd")),
            "macd_signal": _num(ind.get("macd_signal")),
            "macd_hist": _num(ind.get("macd_hist")),
        })
    return rows


def _enrich_trade_log(trades: list[dict], signals) -> list[dict]:
    if not trades:
        return []
    import pandas as pd

    lookup = {}
    for ts, row in signals.iterrows():
        stamp = pd.Timestamp(ts)
        stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
        key = stamp.isoformat()
        lookup[key] = row

    def find_row(value):
        if not value:
            return None
        try:
            stamp = pd.Timestamp(value)
            stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
            key = stamp.isoformat()
        except Exception:
            return None
        return lookup.get(key)

    out = []
    for trade in trades:
        item = dict(trade)
        entry = find_row(item.get("entry_ts"))
        exit_ = find_row(item.get("exit_ts") or item.get("mark_ts"))
        if entry is not None:
            item["entry_p_meta"] = _num(entry.get("p_meta"))
            item["entry_p_swarm"] = _num(entry.get("p_swarm"))
        if exit_ is not None:
            item["exit_p_meta"] = _num(exit_.get("p_meta"))
            item["exit_p_swarm"] = _num(exit_.get("p_swarm"))
        out.append(item)
    return out


def _technical_indicators(ohlcv):
    import numpy as np
    import pandas as pd

    df = ohlcv.copy()
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)

    out = pd.DataFrame(index=df.index)
    out["ema_9"] = close.ewm(span=9, adjust=False).mean()
    out["ema_12"] = close.ewm(span=12, adjust=False).mean()
    out["ema_26"] = close.ewm(span=26, adjust=False).mean()

    high9 = high.rolling(9, min_periods=1).max()
    low9 = low.rolling(9, min_periods=1).min()
    spread = (high9 - low9).replace(0, np.nan)
    rsv = ((close - low9) / spread * 100.0).replace([np.inf, -np.inf], np.nan).fillna(50.0)
    out["kdj_k"] = rsv.ewm(alpha=1 / 3, adjust=False).mean()
    out["kdj_d"] = out["kdj_k"].ewm(alpha=1 / 3, adjust=False).mean()
    out["kdj_j"] = 3 * out["kdj_k"] - 2 * out["kdj_d"]

    out["highest_9"] = high9
    out["lowest_9"] = low9
    out["macd"] = out["ema_12"] - out["ema_26"]
    out["macd_signal"] = out["macd"].ewm(span=9, adjust=False).mean()
    out["macd_hist"] = out["macd"] - out["macd_signal"]
    return out


def _num(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _build_pro_series(equity_curve: list[dict]) -> dict:
    """Compute drawdown / rolling Sharpe / rolling vol / monthly heatmap series."""
    if not equity_curve:
        return {"drawdown_series": [], "rolling_sharpe": [], "rolling_vol": [], "monthly_returns": []}
    try:
        import pandas as pd
        from .backtest.pro_metrics import build_pro_series

        df = pd.DataFrame(equity_curve)
        if "value" not in df or "ts" not in df:
            return {"drawdown_series": [], "rolling_sharpe": [], "rolling_vol": [], "monthly_returns": []}
        df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
        df = df.dropna(subset=["ts", "value"]).sort_values("ts")
        if df.empty:
            return {"drawdown_series": [], "rolling_sharpe": [], "rolling_vol": [], "monthly_returns": []}
        s = pd.Series(df["value"].astype(float).values, index=df["ts"])
        returns = s.pct_change().dropna()
        window = min(90, max(20, len(returns) // 4))
        return build_pro_series(returns, rolling_window=window, freq="1d")
    except Exception as exc:  # noqa: BLE001
        logger.warning("build_pro_series failed: %s", exc)
        return {"drawdown_series": [], "rolling_sharpe": [], "rolling_vol": [], "monthly_returns": []}


def _build_pro_distributions(trade_log: list[dict]) -> dict:
    try:
        from .backtest.pro_metrics import trade_distributions

        return trade_distributions(trade_log or [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("trade_distributions failed: %s", exc)
        return {"pnl_hist": [], "duration_hist": [], "by_side": {}}


def _text(value, fallback: str) -> str:
    if value is None:
        return fallback
    try:
        if value != value:
            return fallback
    except Exception:
        pass
    text = str(value)
    return text if text else fallback


def _get(row, key: str):
    try:
        return row.get(key)
    except AttributeError:
        return None
