"""Paper-trading API blueprint (multi-asset simulated matching)."""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

paper_trading_bp = Blueprint("paper_trading", __name__)
logger = logging.getLogger(__name__)


def _lazy_portfolio():
    from app.quant.paper_trading import portfolio
    return portfolio


def _lazy_registry():
    from app.quant.data import symbol_registry
    return symbol_registry


@paper_trading_bp.get("/symbols")
def list_symbols():
    return jsonify({"symbols": [s.to_dict() for s in _lazy_registry().list_symbols()]})


@paper_trading_bp.post("/accounts")
def create_account():
    body = request.get_json(silent=True) or {}
    name = body.get("name") or "Paper Account"
    initial_cash = float(body.get("initial_cash") or 100000.0)
    ccy = body.get("ccy", "USD")
    return jsonify(_lazy_portfolio().create_account(name=name,
                                                   initial_cash=initial_cash,
                                                   ccy=ccy)), 201


@paper_trading_bp.get("/accounts")
def list_accounts():
    return jsonify({"accounts": _lazy_portfolio().list_accounts()})


@paper_trading_bp.get("/accounts/<account_id>")
def get_account(account_id):
    try:
        return jsonify(_lazy_portfolio().snapshot(account_id))
    except FileNotFoundError:
        return jsonify({"error": "not found"}), 404


@paper_trading_bp.delete("/accounts/<account_id>")
def delete_account(account_id):
    try:
        return jsonify(_lazy_portfolio().delete_account(account_id)), 200
    except FileNotFoundError:
        return jsonify({"error": "not found"}), 404
    except Exception as exc:  # noqa: BLE001
        logger.exception("delete_account failed")
        return jsonify({"error": str(exc)}), 500


@paper_trading_bp.get("/accounts/<account_id>/orders")
def list_orders(account_id):
    try:
        doc = _lazy_portfolio().get_account(account_id)
        return jsonify({"orders": doc.get("orders", [])})
    except FileNotFoundError:
        return jsonify({"error": "not found"}), 404


@paper_trading_bp.post("/accounts/<account_id>/orders")
def place_order(account_id):
    body = request.get_json(silent=True) or {}

    def _num(key):
        val = body.get(key)
        if val in (None, ""):
            return None
        return float(val)

    try:
        order = _lazy_portfolio().place_order(
            account_id=account_id,
            symbol=body.get("symbol"),
            side=body.get("side"),
            qty=float(body.get("qty") or 0),
            order_type=body.get("order_type", "market"),
            limit_price=_num("limit_price"),
            stop_price=_num("stop_price"),
            trail_amount=_num("trail_amount"),
            trail_percent=_num("trail_percent"),
            take_profit=_num("take_profit"),
            stop_loss=_num("stop_loss"),
            reduce_only=bool(body.get("reduce_only", False)),
        )
        return jsonify(order), 201
    except FileNotFoundError:
        return jsonify({"error": "account not found"}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        logger.exception("place_order failed")
        return jsonify({"error": str(exc)}), 500


@paper_trading_bp.delete("/accounts/<account_id>/orders/<order_id>")
def cancel_order(account_id, order_id):
    try:
        return jsonify(_lazy_portfolio().cancel_order(account_id, order_id)), 200
    except FileNotFoundError:
        return jsonify({"error": "order not found"}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        logger.exception("cancel_order failed")
        return jsonify({"error": str(exc)}), 500


@paper_trading_bp.get("/accounts/<account_id>/equity-curve")
def equity_curve(account_id):
    try:
        doc = _lazy_portfolio().get_account(account_id)
        return jsonify({"equity_curve": doc.get("equity_curve", [])})
    except FileNotFoundError:
        return jsonify({"error": "not found"}), 404


def _lazy_auto_trader():
    from app.quant.paper_trading import auto_trader
    return auto_trader


@paper_trading_bp.get("/auto-trade/config")
def auto_trade_config():
    """Expose the auto-trader gating thresholds so the UI can explain the strategy."""
    from app.quant import config as quant_config

    return jsonify({
        "score_threshold": quant_config.AUTO_TRADE_SCORE_THRESHOLD,
        "min_confidence": quant_config.AUTO_TRADE_MIN_CONFIDENCE,
        "max_position_pct": quant_config.AUTO_TRADE_MAX_POSITION_PCT,
        "cash_reserve_pct": quant_config.AUTO_TRADE_CASH_RESERVE_PCT,
    })


@paper_trading_bp.get("/signals/fused/<path:symbol>")
def fused_signal(symbol):
    """Return the fused multi-source signal used by the auto-trader."""
    try:
        from app.quant.paper_trading import signal_fusion

        return jsonify(signal_fusion.fuse(symbol))
    except Exception as exc:  # noqa: BLE001
        logger.exception("fused signal failed")
        return jsonify({"error": str(exc)}), 500


@paper_trading_bp.post("/accounts/<account_id>/auto-trade/run")
def run_auto_trade(account_id):
    """Manually trigger one auto-trading cycle for an account.

    Optional JSON body: ``{"watchlist": ["AAPL", "BTC-USDT"]}`` to override
    the configured default universe for this run only.
    """
    body = request.get_json(silent=True) or {}
    watchlist = body.get("watchlist")
    if watchlist is not None and not isinstance(watchlist, list):
        return jsonify({"error": "watchlist must be a list of symbols"}), 400
    try:
        result = _lazy_auto_trader().run_cycle(account_id, watchlist=watchlist)
        if result.get("error"):
            return jsonify(result), 404
        return jsonify(result), 200
    except Exception as exc:  # noqa: BLE001
        logger.exception("auto-trade run failed")
        return jsonify({"error": str(exc)}), 500


def _lazy_task_runner():
    from app.quant.paper_trading import task_runner
    return task_runner


@paper_trading_bp.post("/accounts/<account_id>/auto-trade/start")
def start_auto_trade(account_id):
    """Start one auto-trading cycle in the background and return a task id.

    The synchronous ``/auto-trade/run`` endpoint can exceed the frontend HTTP
    timeout because every symbol triggers an LLM forecast. This non-blocking
    variant returns immediately; clients poll ``/auto-trade/tasks/<task_id>``.
    """
    body = request.get_json(silent=True) or {}
    watchlist = body.get("watchlist")
    if watchlist is not None and not isinstance(watchlist, list):
        return jsonify({"error": "watchlist must be a list of symbols"}), 400
    # Validate the account exists up front so the client gets a fast 404.
    try:
        _lazy_portfolio().get_account(account_id)
    except FileNotFoundError:
        return jsonify({"error": "account not found"}), 404
    task_id = _lazy_task_runner().start_auto_trade(account_id, watchlist)
    return jsonify({"task_id": task_id, "status": "running"}), 202


@paper_trading_bp.get("/auto-trade/tasks/<task_id>")
def auto_trade_task(task_id):
    task = _lazy_task_runner().get(task_id)
    if task is None:
        return jsonify({"error": "task not found"}), 404
    return jsonify(task), 200


@paper_trading_bp.get("/ohlcv/<path:symbol>")
def ohlcv(symbol):
    """Return OHLCV candles for charting (TradingView Lightweight Charts).

    Query params: ``tf`` (timeframe: ``1d`` default, ``1h``/``4h``) and ``days``
    (lookback window). Time is emitted as UNIX seconds (UTC).
    """
    from datetime import datetime, timedelta, timezone

    tf = (request.args.get("tf") or "1d").lower()
    if tf not in {"1d", "1h", "4h"}:
        tf = "1d"
    try:
        days = int(request.args.get("days") or (60 if tf != "1d" else 365))
    except (TypeError, ValueError):
        days = 365
    days = max(1, min(days, 1825))

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    try:
        from app.quant.data import market_data

        df = market_data.fetch_ohlcv(symbol, start, end, freq=tf)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ohlcv fetch failed for %s: %s", symbol, exc)
        return jsonify({"symbol": symbol, "tf": tf, "candles": [],
                        "error": str(exc), "stale": True}), 200

    candles = []
    for ts, row in df.iterrows():
        candles.append({
            "time": int(ts.timestamp()),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row.get("volume", 0.0) or 0.0),
        })
    quality = df.attrs.get("data_quality", {}) if hasattr(df, "attrs") else {}
    return jsonify({
        "symbol": symbol, "tf": tf, "candles": candles,
        "stale": bool(quality.get("error") == "stale_fallback"),
        "source": quality.get("data_source"),
    })


@paper_trading_bp.get("/quotes/<path:symbol>")
def quote(symbol):
    portfolio = _lazy_portfolio()
    try:
        price = portfolio.latest_quote(symbol)
        return jsonify({"symbol": symbol, "price": price, "stale": False})
    except Exception as exc:  # noqa: BLE001
        # Graceful degradation: never 500 a quote. Fall back to the last known
        # (possibly stale) price so the trading UI keeps rendering.
        fallback = portfolio.last_known_price(symbol)
        if fallback is not None:
            return jsonify({"symbol": symbol, "price": fallback, "stale": True})
        logger.warning("quote unavailable for %s: %s", symbol, exc)
        return jsonify({"symbol": symbol, "price": None, "stale": True,
                        "error": str(exc)}), 200


@paper_trading_bp.get("/signals/<path:symbol>")
def latest_signal(symbol):
    try:
        from app.quant import pipeline

        return jsonify(pipeline.latest_signal(symbol))
    except FileNotFoundError:
        return jsonify({"error": "no quant signal for symbol"}), 404
    except Exception as exc:  # noqa: BLE001
        logger.exception("latest quant signal failed")
        return jsonify({"error": str(exc)}), 500


@paper_trading_bp.get("/accounts/<account_id>/weekly")
def account_weekly(account_id):
    """Return last-7-day equity / signals / predicted-vs-actual / trades."""
    from datetime import datetime, timedelta, timezone

    try:
        doc = _lazy_portfolio().get_account(account_id)
    except FileNotFoundError:
        return jsonify({"error": "not found"}), 404

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    def _parse(ts):
        try:
            return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except Exception:  # noqa: BLE001
            return None

    eq_curve = [p for p in (doc.get("equity_curve") or []) if (_parse(p.get("ts")) or cutoff) >= cutoff]
    orders = [o for o in (doc.get("orders") or []) if (_parse(o.get("ts") or o.get("created_at")) or cutoff) >= cutoff]
    trades = [t for t in (doc.get("trades") or []) if (_parse(t.get("ts") or t.get("filled_at")) or cutoff) >= cutoff]

    # Aggregate signals + predicted vs actual per held symbol
    symbols = sorted({(o.get("symbol") or "").upper() for o in orders if o.get("symbol")})
    signals_7d = []
    predicted_vs_actual_7d = []
    try:
        from app.quant import pipeline
        for sym in symbols:
            try:
                sig = pipeline.latest_signal(sym)
                signals_7d.append({"symbol": sym, "signal": sig})
                if sig and sig.get("predicted_price") is not None:
                    predicted_vs_actual_7d.append({
                        "symbol": sym,
                        "predicted_price": sig.get("predicted_price"),
                        "predicted_band_low": sig.get("predicted_band_low"),
                        "predicted_band_high": sig.get("predicted_band_high"),
                        "last_close": sig.get("last_close"),
                        "as_of": sig.get("as_of"),
                    })
            except FileNotFoundError:
                continue
            except Exception as exc:  # noqa: BLE001
                logger.debug("signal lookup failed for %s: %s", sym, exc)
    except Exception as exc:  # noqa: BLE001
        logger.debug("pipeline import failed: %s", exc)

    return jsonify({
        "account_id": account_id,
        "as_of": _now_iso() if (_now_iso := getattr(_lazy_portfolio(), "_now_iso", None)) else None,
        "window": "7d",
        "equity_curve_7d": eq_curve,
        "trades_7d": trades,
        "orders_7d": orders,
        "signals_7d": signals_7d,
        "predicted_vs_actual_7d": predicted_vs_actual_7d,
        "summary": {
            "trade_count": len(trades),
            "order_count": len(orders),
            "symbols": symbols,
        },
    })
