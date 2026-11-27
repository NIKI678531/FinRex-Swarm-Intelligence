"""FMP News & Social Sentiment API routes.

Exposes the FMP `stable` news + social-sentiment surface to the frontend
through a single blueprint `/api/fmp/news`.
"""

from __future__ import annotations

import logging
import traceback
from typing import Any

from flask import Blueprint, jsonify, request

from ..services.fmp.news_client import get_client

logger = logging.getLogger("finrex.api.fmp_news")

fmp_news_bp = Blueprint("fmp_news", __name__)


def _query_int(name: str, default: int, min_val: int = 0, max_val: int = 200) -> int:
    raw = request.args.get(name, default, type=int)
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return default
    return max(min_val, min(val, max_val))


def _query_str(name: str, default: str | None = None) -> str | None:
    val = request.args.get(name)
    return val if val else default


def _ok(items: list[dict], extra: dict | None = None) -> Any:
    payload = {"success": True, "data": {"items": items, "count": len(items)}}
    if extra:
        payload["data"].update(extra)
    return jsonify(payload)


def _err(msg: str, status: int = 502) -> Any:
    return jsonify({"success": False, "error": msg}), status


# --------------------------------------------------------------------------- #
# news endpoints                                                              #
# --------------------------------------------------------------------------- #

@fmp_news_bp.route("/general", methods=["GET"])
def general():
    page, limit = _query_int("page", 0), _query_int("limit", 50, 1, 100)
    try:
        items = get_client().news_general(page=page, limit=limit,
                                          from_=_query_str("from"), to=_query_str("to"))
        return _ok(items)
    except Exception as exc:  # noqa: BLE001
        logger.warning("FMP general failed: %s", exc)
        return _err(str(exc))


@fmp_news_bp.route("/stock", methods=["GET"])
def stock():
    try:
        symbols = _query_str("symbols") or _query_str("tickers") or _query_str("symbol")
        items = get_client().news_stock(
            tickers=symbols,
            page=_query_int("page", 0),
            limit=_query_int("limit", 50, 1, 100),
            from_=_query_str("from"), to=_query_str("to"),
        )
        return _ok(items, extra={"symbols": symbols or "", "mode": "symbol" if symbols else "latest"})
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


@fmp_news_bp.route("/stock-latest", methods=["GET"])
def stock_latest():
    try:
        items = get_client().news_stock_latest(page=_query_int("page", 0),
                                               limit=_query_int("limit", 50, 1, 100))
        return _ok(items)
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


@fmp_news_bp.route("/crypto", methods=["GET"])
def crypto():
    try:
        items = get_client().news_crypto(
            symbols=_query_str("symbols"),
            page=_query_int("page", 0),
            limit=_query_int("limit", 50, 1, 100),
            from_=_query_str("from"), to=_query_str("to"),
        )
        return _ok(items)
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


@fmp_news_bp.route("/crypto-latest", methods=["GET"])
def crypto_latest():
    try:
        items = get_client().news_crypto_latest(page=_query_int("page", 0),
                                                limit=_query_int("limit", 50, 1, 100))
        return _ok(items)
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


@fmp_news_bp.route("/forex", methods=["GET"])
def forex():
    try:
        items = get_client().news_forex(
            symbols=_query_str("symbols"),
            page=_query_int("page", 0),
            limit=_query_int("limit", 50, 1, 100),
            from_=_query_str("from"), to=_query_str("to"),
        )
        return _ok(items)
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


@fmp_news_bp.route("/forex-latest", methods=["GET"])
def forex_latest():
    try:
        items = get_client().news_forex_latest(page=_query_int("page", 0),
                                               limit=_query_int("limit", 50, 1, 100))
        return _ok(items)
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


@fmp_news_bp.route("/press-releases", methods=["GET"])
def press_releases():
    try:
        items = get_client().news_press_releases(
            symbols=_query_str("symbols"),
            page=_query_int("page", 0),
            limit=_query_int("limit", 50, 1, 100),
            from_=_query_str("from"), to=_query_str("to"),
        )
        return _ok(items)
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


@fmp_news_bp.route("/press-releases-latest", methods=["GET"])
def press_releases_latest():
    try:
        items = get_client().news_press_releases_latest(
            page=_query_int("page", 0), limit=_query_int("limit", 50, 1, 100)
        )
        return _ok(items)
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


@fmp_news_bp.route("/search", methods=["GET"])
def search():
    q = _query_str("q") or _query_str("query")
    if not q:
        return _err("q parameter required", 400)
    try:
        items = get_client().news_search(
            query=q,
            page=_query_int("page", 0),
            limit=_query_int("limit", 30, 1, 100),
            from_=_query_str("from"), to=_query_str("to"),
        )
        return _ok(items, extra={"query": q})
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


@fmp_news_bp.route("/articles", methods=["GET"])
def articles():
    try:
        items = get_client().articles(page=_query_int("page", 0),
                                      size=_query_int("size", 20, 1, 100))
        return _ok(items)
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


@fmp_news_bp.route("/fmp-articles", methods=["GET"])
def fmp_articles_route():
    try:
        items = get_client().fmp_articles(page=_query_int("page", 0),
                                          size=_query_int("size", 20, 1, 100))
        return _ok(items)
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


# --------------------------------------------------------------------------- #
# social sentiment                                                            #
# --------------------------------------------------------------------------- #

@fmp_news_bp.route("/social-sentiment/historical", methods=["GET"])
def social_historical():
    symbol = _query_str("symbol")
    if not symbol:
        return _err("symbol parameter required", 400)
    try:
        items = get_client().historical_social_sentiment(symbol=symbol,
                                                         page=_query_int("page", 0))
        return _ok(items, extra={"symbol": symbol})
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


@fmp_news_bp.route("/social-sentiment/trending", methods=["GET"])
def social_trending():
    try:
        items = get_client().social_sentiment_trending(
            type_=_query_str("type") or "bullish",
            source=_query_str("source") or "stocktwits",
        )
        return _ok(items)
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


@fmp_news_bp.route("/social-sentiment/changes", methods=["GET"])
def social_changes():
    try:
        items = get_client().social_sentiment_changes(
            type_=_query_str("type") or "bullish",
            source=_query_str("source") or "stocktwits",
        )
        return _ok(items)
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


# --------------------------------------------------------------------------- #
# health                                                                      #
# --------------------------------------------------------------------------- #

@fmp_news_bp.route("/health", methods=["GET"])
def health():
    from ..config import Config
    return jsonify({
        "success": True,
        "data": {
            "api_key_configured": bool(getattr(Config, "FMP_API_KEY", None)),
            "endpoints": [
                "general", "stock", "stock-latest", "crypto", "crypto-latest",
                "forex", "forex-latest", "press-releases", "press-releases-latest",
                "search", "articles", "fmp-articles",
                "social-sentiment/historical", "social-sentiment/trending", "social-sentiment/changes",
            ],
        },
    })
