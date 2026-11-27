"""Reddit 帖子 API（按 symbol 公开 JSON）。"""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from ..services.financial.reddit_provider import RedditProvider

logger = logging.getLogger("finrex.api.reddit_news")

reddit_news_bp = Blueprint("reddit_news", __name__)


@reddit_news_bp.route("/posts", methods=["GET"])
def posts():
    symbol = (request.args.get("symbol") or "").strip()
    subs_raw = (request.args.get("subreddits") or "").strip()
    subs = [s.strip() for s in subs_raw.split(",") if s.strip()] or None
    try:
        limit_per_sub = int(request.args.get("limit_per_sub", 8))
    except (TypeError, ValueError):
        limit_per_sub = 8
    limit_per_sub = max(3, min(limit_per_sub, 25))

    res = RedditProvider.fetch_posts(
        symbol=symbol,
        subreddits=subs,
        limit_per_sub=limit_per_sub,
    )
    return jsonify({
        "success": bool(res.get("ok")),
        "data": {
            "items": res.get("items") or [],
            "count": len(res.get("items") or []),
            "source": res.get("source", "reddit_public"),
            "symbol": symbol.upper() if symbol else "",
            "mode": "symbol" if symbol else "latest",
        },
        "error": res.get("error"),
    })
