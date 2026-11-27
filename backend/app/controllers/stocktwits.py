"""StockTwits 流 API。"""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from ..services.financial.stocktwits_provider import StockTwitsProvider

logger = logging.getLogger("finrex.api.stocktwits")

stocktwits_bp = Blueprint("stocktwits", __name__)


@stocktwits_bp.route("/stream", methods=["GET"])
def stream():
    symbol = (request.args.get("symbol") or "").strip()
    try:
        limit = int(request.args.get("limit", 30))
    except (TypeError, ValueError):
        limit = 30
    limit = max(1, min(limit, 50))

    res = StockTwitsProvider.fetch_stream(symbol=symbol, limit=limit)
    return jsonify({
        "success": bool(res.get("ok")),
        "data": {
            "items": res.get("items") or [],
            "count": len(res.get("items") or []),
            "source": res.get("source", "stocktwits"),
            "symbol": symbol.upper() if symbol else "",
            "mode": "symbol" if symbol else "trending",
        },
        "error": res.get("error"),
    })
