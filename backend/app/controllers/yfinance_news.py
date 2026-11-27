"""yfinance 新闻 API。"""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from ..services.financial.yfinance_news_provider import YFinanceNewsProvider

logger = logging.getLogger("finrex.api.yfinance_news")

yfinance_news_bp = Blueprint("yfinance_news", __name__)


@yfinance_news_bp.route("/news", methods=["GET"])
def news():
    symbol = (request.args.get("symbol") or "").strip()
    try:
        limit = int(request.args.get("limit", 15))
    except (TypeError, ValueError):
        limit = 15
    limit = max(1, min(limit, 50))
    res = YFinanceNewsProvider.fetch(symbol=symbol, limit=limit)
    if not res["ok"]:
        return jsonify({
            "success": False,
            "data": {"items": [], "count": 0, "source": res.get("source")},
            "error": res.get("error"),
        }), 502 if res.get("error") else 200
    return jsonify({
        "success": True,
        "data": {
            "items": res["items"],
            "count": len(res["items"]),
            "source": res.get("source", "yfinance"),
            "symbol": symbol.upper() if symbol else "",
            "mode": "symbol" if symbol else "market",
        },
    })
