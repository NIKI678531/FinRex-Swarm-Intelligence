"""REST endpoints for the CSOP ETF asset allocation dashboard.

Routes:
    GET  /api/report/<report_id>/asset-allocation        — full bundle
    POST /api/report/<report_id>/asset-allocation        — force regenerate
    GET  /api/asset-allocation/etf/<code>/forecast       — single ETF detail

These all live under a dedicated blueprint so they can be skipped at
import time if optional dependencies (yfinance / pyyaml) are missing.
"""

from __future__ import annotations

import logging
import traceback
from typing import Any, Dict

from flask import Blueprint, jsonify, request

from ..services.asset_forecast import AssetForecastService
from ..services.report_agent import ReportManager

logger = logging.getLogger("finrex.api.asset_allocation")

asset_allocation_bp = Blueprint("asset_allocation", __name__)


def _err(msg: str, status: int = 400, **extra: Any):
    payload: Dict[str, Any] = {"success": False, "error": msg}
    payload.update(extra)
    return jsonify(payload), status


# ---------------------------------------------------------------------------


def _parse_horizon(value: Any, default: int = 5) -> int:
    """Accept '1w' / '2w' / '1m' / int days; default 5 trading days."""
    if value is None or value == "":
        return default
    try:
        s = str(value).strip().lower()
        mapping = {"1w": 5, "2w": 10, "1m": 21, "week": 5, "month": 21}
        if s in mapping:
            return mapping[s]
        return max(1, min(60, int(s)))
    except Exception:
        return default


@asset_allocation_bp.route("/report/<report_id>/asset-allocation", methods=["GET"])
def get_report_asset_allocation(report_id: str):
    """Return cached bundle, or build one if missing."""
    try:
        horizon = _parse_horizon(request.args.get("horizon"))
        force = request.args.get("force") in ("1", "true", "yes")
        bundle = None if force else AssetForecastService.get_bundle(report_id)
        # If cache exists but uses a different horizon than requested, rebuild.
        if bundle and int(bundle.get("horizon_days") or 5) != horizon:
            bundle = None
        if not bundle:
            report = ReportManager.get_report(report_id)
            if not report:
                return _err(f"report {report_id} not found", 404)
            bundle = AssetForecastService.build_for_report(
                report.to_dict(),
                force=True,
                horizon_days=horizon,
            )
        return jsonify({"success": True, "data": bundle})
    except Exception as exc:  # pragma: no cover
        logger.error("get asset-allocation failed: %s", exc)
        return _err(str(exc), 500, traceback=traceback.format_exc())


@asset_allocation_bp.route("/report/<report_id>/asset-allocation", methods=["POST"])
def regenerate_report_asset_allocation(report_id: str):
    """Force-regenerate the bundle for a report."""
    try:
        payload = request.get_json(silent=True) or {}
        report = ReportManager.get_report(report_id)
        if not report:
            return _err(f"report {report_id} not found", 404)
        bundle = AssetForecastService.build_for_report(
            report.to_dict(),
            force=True,
            top_n=int(payload.get("top_n") or 8),
            horizon_days=_parse_horizon(payload.get("horizon") or payload.get("horizon_days")),
        )
        return jsonify({"success": True, "data": bundle})
    except Exception as exc:  # pragma: no cover
        logger.error("regenerate asset-allocation failed: %s", exc)
        return _err(str(exc), 500, traceback=traceback.format_exc())


@asset_allocation_bp.route("/asset-allocation/etf/<code>/forecast", methods=["GET"])
def get_single_etf_forecast(code: str):
    """Detailed forecast + recent OHLCV tail for a single ETF (drawer)."""
    try:
        lookback = int(request.args.get("lookback_days") or 365)
        horizon = _parse_horizon(request.args.get("horizon"))
        result = AssetForecastService.forecast_single(code, lookback_days=lookback, horizon_days=horizon)
        if not result.get("ok"):
            return jsonify({"success": False, "data": result}), 200
        return jsonify({"success": True, "data": result})
    except Exception as exc:  # pragma: no cover
        logger.error("single ETF forecast failed: %s", exc)
        return _err(str(exc), 500, traceback=traceback.format_exc())


