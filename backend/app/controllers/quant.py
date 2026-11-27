"""Quant API blueprint — unified strategy backtest."""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

quant_bp = Blueprint("quant", __name__)
logger = logging.getLogger(__name__)


def _lazy_pipeline():
    from app.quant import pipeline  # heavy imports happen inside
    return pipeline


def _lazy_registry():
    from app.quant.data import symbol_registry
    return symbol_registry


def _bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@quant_bp.get("/symbols")
def list_symbols():
    reg = _lazy_registry()
    return jsonify({"symbols": [s.to_dict() for s in reg.list_symbols()]})


@quant_bp.get("/backtest/runs")
def list_runs():
    return jsonify({"runs": _lazy_pipeline().list_runs()})


@quant_bp.post("/backtest/runs")
def create_run():
    body = request.get_json(silent=True) or {}
    symbol = body.get("symbol")
    start = body.get("start")
    end = body.get("end")
    horizon = int(body.get("horizon") or 5)
    initial_cash = float(body.get("initial_cash") or 10000.0)
    fee_bps = float(body.get("fee_bps") if body.get("fee_bps") is not None else 5.0)
    exposure = float(body.get("exposure") if body.get("exposure") is not None else 0.95)
    signal_threshold = float(body.get("signal_threshold") if body.get("signal_threshold") is not None else 0.0)
    allow_short = _bool(body.get("allow_short"), True)
    train_days = int(body["train_days"]) if body.get("train_days") else None
    test_days = int(body["test_days"]) if body.get("test_days") else None
    step_days = int(body["step_days"]) if body.get("step_days") else None
    model_family = body.get("model_family")
    if not model_family:
        model_kind = str(body.get("model_kind") or "").strip().lower()
        model_family = body.get("model_kind") if model_kind in {
            "price_point_calibrated_ml",
            "price_point_ml",
            "calibrated_ml",
            "calibrated_price_ml",
            "price_point_calibrated",
            "price_forecast_ml",
            "price_forecast",
            "financial_forecast",
            "financial_sentiment",
            "two_tower",
            "dual_tower",
            "hybrid_alpha",
            "market_swarm",
            "legacy",
        } else "price_point_calibrated_ml"
    swarm_source_mode = str(body.get("swarm_source_mode") or "auto").lower()
    if swarm_source_mode not in {"auto", "fmp_only", "oasis_only"}:
        return jsonify({"error": "swarm_source_mode must be auto, fmp_only, or oasis_only"}), 400
    oasis_simulation_id = body.get("oasis_simulation_id") or None
    sentiment_sources = body.get("sentiment_sources") or ["fmp"]
    if isinstance(sentiment_sources, str):
        sentiment_sources = [sentiment_sources]
    if not symbol or not start or not end:
        return jsonify({"error": "symbol, start, end are required"}), 400
    try:
        result = _lazy_pipeline().run_backtest(
            symbol=symbol, start=start, end=end,
            horizon=horizon, initial_cash=initial_cash,
            swarm_source_mode=swarm_source_mode,
            oasis_simulation_id=oasis_simulation_id,
            sentiment_sources=sentiment_sources,
            fee_bps=fee_bps,
            exposure=exposure,
            allow_short=allow_short,
            signal_threshold=signal_threshold,
            train_days=train_days,
            test_days=test_days,
            step_days=step_days,
            model_family=model_family,
        )
        return jsonify(result), 201
    except Exception as exc:  # noqa: BLE001
        logger.exception("quant backtest failed")
        return jsonify({"error": str(exc)}), 500


@quant_bp.get("/backtest/runs/<run_id>")
def get_run(run_id):
    try:
        return jsonify(_lazy_pipeline().get_run(run_id))
    except FileNotFoundError:
        return jsonify({"error": "not found"}), 404


@quant_bp.get("/backtest/runs/<run_id>/equity-curve")
def get_equity_curve(run_id):
    try:
        data = _lazy_pipeline().get_run(run_id)
        return jsonify({"equity_curve": data.get("equity_curve", [])})
    except FileNotFoundError:
        return jsonify({"error": "not found"}), 404


@quant_bp.get("/backtest/runs/<run_id>/trades")
def get_trades(run_id):
    try:
        data = _lazy_pipeline().get_run(run_id)
        return jsonify({"trades": data.get("trades", [])})
    except FileNotFoundError:
        return jsonify({"error": "not found"}), 404


@quant_bp.delete("/backtest/runs/<run_id>")
def delete_run(run_id):
    ok = _lazy_pipeline().delete_run(run_id)
    if not ok:
        return jsonify({"error": "not found"}), 404
    return jsonify({"ok": True})
