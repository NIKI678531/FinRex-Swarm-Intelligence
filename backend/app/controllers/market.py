"""Shared BTC market-data API for Validation and Backtest desks."""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from ..services.market import binance_market

logger = logging.getLogger("finrex.api.market")

market_bp = Blueprint("market", __name__)


@market_bp.get("/btc/ohlcv")
def btc_ohlcv():
    try:
        interval = request.args.get("interval", "1h")
        lookback = request.args.get("lookback", "7d")
        return jsonify({"success": True, "data": binance_market.ohlcv(interval=interval, lookback=lookback)})
    except Exception as exc:
        logger.exception("btc ohlcv failed")
        return jsonify({"success": False, "error": str(exc)}), 400


@market_bp.get("/btc/ticker")
def btc_ticker():
    try:
        return jsonify({"success": True, "data": binance_market.ticker()})
    except Exception as exc:
        logger.exception("btc ticker failed")
        return jsonify({"success": False, "error": str(exc)}), 502


@market_bp.get("/btc/depth")
def btc_depth():
    try:
        return jsonify({"success": True, "data": binance_market.depth(limit=int(request.args.get("limit", 20)))})
    except Exception as exc:
        logger.exception("btc depth failed")
        return jsonify({"success": False, "error": str(exc)}), 502


@market_bp.get("/btc/trades")
def btc_trades():
    try:
        return jsonify({"success": True, "data": binance_market.trades(limit=int(request.args.get("limit", 50)))})
    except Exception as exc:
        logger.exception("btc trades failed")
        return jsonify({"success": False, "error": str(exc)}), 502

