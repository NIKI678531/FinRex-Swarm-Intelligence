"""Financial forecast APIs."""

from __future__ import annotations

import traceback
from typing import Any, Dict

from flask import jsonify, request

from . import financial_bp
from ..services.financial.crypto_forecast_service import CryptoForecastService
from ..utils.logger import get_logger

logger = get_logger("finrex.api.financial")


def _err(message: str, status: int = 400, **extra: Any):
    payload: Dict[str, Any] = {"success": False, "error": message}
    payload.update(extra)
    return jsonify(payload), status


@financial_bp.route("/crypto-forecast", methods=["GET", "POST"])
def crypto_forecast():
    """Return a structured crypto one-week directional forecast.

    GET query:  symbol=BTC&horizon=1w
    POST JSON:  {symbol, horizon, comments, articles}
    """
    try:
        if request.method == "POST":
            payload = request.get_json(silent=True) or {}
        else:
            payload = {}
        symbol = (payload.get("symbol") if payload else None) or request.args.get("symbol") or "BTC"
        horizon = (payload.get("horizon") if payload else None) or request.args.get("horizon") or "1w"
        comments = payload.get("comments") if isinstance(payload, dict) else None
        articles = payload.get("articles") if isinstance(payload, dict) else None
        service = CryptoForecastService()
        result = service.forecast(symbol=symbol, horizon=horizon, comments=comments, articles=articles)
        return jsonify({"success": True, "data": result})
    except Exception as exc:  # noqa: BLE001
        logger.error("crypto forecast failed: %s", exc)
        return _err(str(exc), 500, traceback=traceback.format_exc())
