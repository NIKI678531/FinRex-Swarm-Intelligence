"""Weekly Validation Lab API.

Mounted at `/api/validation`.

Endpoints:
    GET  /cycle/current                - get/create current week cycle
    POST /snapshot                     - run a fresh forecast + place bets
    GET  /forecast/latest              - latest forecast for current cycle
    GET  /positions?status=...         - list positions across cycles
    GET  /kpi                          - KPI strip metrics
    GET  /equity-curve                 - per-cycle equity history
    POST /settle                       - manually settle due cycles
    POST /admin/force-settle           - force-settle current cycle (debug)
"""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from ..services.validation import weekly_engine
from ..services.validation.model_registry import list_models as _list_models
from ..services.polymarket.weekly_range_matcher import WeeklyBTCMarketMatcher

logger = logging.getLogger("finrex.api.validation")

validation_bp = Blueprint("validation", __name__)


def _symbol_from_args() -> str:
    return (request.args.get("symbol") or "BTC").upper()


@validation_bp.get("/cycle/current")
def cycle_current():
    try:
        return jsonify({"success": True, "data": weekly_engine.get_or_create_current_cycle(_symbol_from_args())})
    except Exception as exc:
        logger.exception("cycle/current failed")
        return jsonify({"success": False, "error": str(exc)}), 500


@validation_bp.post("/snapshot")
def snapshot():
    body = request.get_json(silent=True) or {}
    symbol = (body.get("symbol") or "BTC").upper()
    n_paths = int(body.get("n_paths") or 5000)
    place_bets = bool(body.get("place_bets", True))
    model_family = body.get("model_family") or body.get("model") or None
    try:
        return jsonify({"success": True, "data": weekly_engine.run_snapshot(
            symbol, n_paths=n_paths, place_bets=place_bets, model_family=model_family,
        )})
    except Exception as exc:
        logger.exception("snapshot failed")
        return jsonify({"success": False, "error": str(exc)}), 500


@validation_bp.get("/models")
def models():
    return jsonify({"success": True, "data": {"items": _list_models()}})


@validation_bp.get("/forecast/latest")
def forecast_latest():
    data = weekly_engine.get_or_create_current_cycle(_symbol_from_args())
    return jsonify({"success": True, "data": data.get("latest_forecast")})


@validation_bp.get("/polymarket/weekly")
def polymarket_weekly():
    mode = request.args.get("mode", "current")
    limit = int(request.args.get("limit", 10))
    try:
        data = WeeklyBTCMarketMatcher().weekly_payload(mode=mode, limit=limit)
        return jsonify({"success": True, "data": data})
    except Exception as exc:
        logger.exception("polymarket weekly failed")
        return jsonify({
            "success": True,
            "data": {
                "current": None,
                "history": [],
                "source_status": {"available": False, "source": "polymarket_gamma_clob", "errors": [str(exc)]},
            },
        })


@validation_bp.get("/positions")
def positions():
    status = request.args.get("status", "all")
    return jsonify({"success": True, "data": {"items": weekly_engine.list_positions(_symbol_from_args(), status)}})


@validation_bp.get("/kpi")
def kpi():
    return jsonify({"success": True, "data": weekly_engine.kpi_summary(_symbol_from_args())})


@validation_bp.get("/equity-curve")
def equity_curve():
    return jsonify({"success": True, "data": {"points": weekly_engine.equity_curve(_symbol_from_args())}})


@validation_bp.post("/settle")
def settle():
    try:
        return jsonify({"success": True, "data": {"settled": weekly_engine.settle_due_cycles(_symbol_from_args())}})
    except Exception as exc:
        logger.exception("settle failed")
        return jsonify({"success": False, "error": str(exc)}), 500


@validation_bp.post("/admin/force-settle")
def force_settle():
    try:
        return jsonify({"success": True, "data": {"settled": weekly_engine.settle_due_cycles(_symbol_from_args(), force=True)}})
    except Exception as exc:
        logger.exception("force-settle failed")
        return jsonify({"success": False, "error": str(exc)}), 500
