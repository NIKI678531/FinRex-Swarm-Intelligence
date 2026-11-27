"""Filesystem-backed paper-trading accounts (no database to keep things lean).

Each account is a JSON document under ``config.PAPER_TRADING_DIR``::

    {
      "account_id": "...",
      "name": "...",
      "ccy": "USD",
      "cash": 100000.0,
      "positions": {"BTC-USDT": {"qty": 1.2, "avg_price": 45000.0}, ...},
      "orders": [...],
      "trades": [...],
      "equity_curve": [...]
    }
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Optional

from .. import config
from ..data import market_data, symbol_registry


def _path(account_id: str) -> Path:
    return config.PAPER_TRADING_DIR / f"{account_id}.json"


def _now_iso() -> str:
    import datetime as dt
    return dt.datetime.now(dt.timezone.utc).isoformat()


def create_account(name: str, initial_cash: float = 100000.0, ccy: str = "USD") -> dict:
    config.ensure_dirs()
    account_id = f"acc_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    doc = {
        "account_id": account_id,
        "name": name,
        "ccy": ccy,
        "cash": float(initial_cash),
        "initial_cash": float(initial_cash),
        "positions": {},
        "orders": [],
        "trades": [],
        "equity_curve": [{"ts": _now_iso(), "value": float(initial_cash)}],
        "created_at": _now_iso(),
    }
    _path(account_id).write_text(json.dumps(doc), encoding="utf-8")
    return doc


def list_accounts() -> "list[dict]":
    config.ensure_dirs()
    out = []
    for f in sorted(config.PAPER_TRADING_DIR.glob("acc_*.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out


def get_account(account_id: str) -> dict:
    fp = _path(account_id)
    if not fp.exists():
        raise FileNotFoundError(account_id)
    return json.loads(fp.read_text(encoding="utf-8"))


def delete_account(account_id: str) -> dict:
    """Permanently delete a paper-trading account file.

    Raises ``FileNotFoundError`` if the account does not exist.
    """
    fp = _path(account_id)
    if not fp.exists():
        raise FileNotFoundError(account_id)
    fp.unlink()
    return {"deleted": account_id}


def _save(doc: dict) -> None:
    _path(doc["account_id"]).write_text(json.dumps(doc), encoding="utf-8")


def latest_quote(symbol: str) -> float:
    """Best-effort latest close from the cached / fresh OHLCV adapter."""
    import datetime as dt
    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(days=10)
    df = market_data.fetch_ohlcv(symbol, start, end)
    if df is None or df.empty:
        raise RuntimeError(f"No quote for {symbol}")
    return float(df["close"].iloc[-1])


def last_known_price(symbol: str) -> Optional[float]:
    """Never-raises last price: live quote first, then any stale disk cache.

    Returns ``None`` only when no price can be sourced at all. Used by the API
    layer to degrade gracefully instead of returning HTTP 500.
    """
    try:
        return latest_quote(symbol)
    except Exception:  # noqa: BLE001
        pass
    try:
        df = market_data._load_stale_cache(symbol, "1d")
        if df is not None and not df.empty:
            return float(df["close"].iloc[-1])
    except Exception:  # noqa: BLE001
        pass
    return None


def _apply_fill(doc: dict, symbol: str, side: str, qty: float, price: float) -> float:
    """Mutate ``doc`` cash/positions for a fill. Returns the traded notional.

    Raises ``ValueError`` on insufficient cash / position.
    """
    notional = qty * price
    if side == "buy":
        if doc["cash"] < notional:
            raise ValueError(
                f"insufficient cash: need {notional:,.2f} but only "
                f"{doc['cash']:,.2f} available"
            )
        doc["cash"] -= notional
        pos = doc["positions"].get(symbol, {"qty": 0.0, "avg_price": 0.0})
        new_qty = pos["qty"] + qty
        pos["avg_price"] = (
            (pos["avg_price"] * pos["qty"] + price * qty) / new_qty
            if new_qty > 0 else 0.0
        )
        pos["qty"] = new_qty
        doc["positions"][symbol] = pos
    else:
        pos = doc["positions"].get(symbol)
        if not pos or pos["qty"] < qty:
            raise ValueError("insufficient position")
        doc["cash"] += notional
        pos["qty"] -= qty
        if pos["qty"] <= 1e-9:
            del doc["positions"][symbol]
    return notional


def _append_mtm(doc: dict) -> None:
    mtm = doc["cash"]
    for sym, p in doc["positions"].items():
        try:
            mtm += p["qty"] * latest_quote(sym)
        except Exception:
            mtm += p["qty"] * p["avg_price"]
    doc["equity_curve"].append({"ts": _now_iso(), "value": float(mtm)})


def place_order(
    account_id: str,
    symbol: str,
    side: str,
    qty: float,
    order_type: str = "market",
    limit_price: Optional[float] = None,
    stop_price: Optional[float] = None,
    trail_amount: Optional[float] = None,
    trail_percent: Optional[float] = None,
    take_profit: Optional[float] = None,
    stop_loss: Optional[float] = None,
    reduce_only: bool = False,
    oco_group: Optional[str] = None,
    meta: Optional[dict] = None,
) -> dict:
    if not symbol_registry.exists(symbol):
        raise ValueError(f"Unknown symbol {symbol}")
    if side not in {"buy", "sell"}:
        raise ValueError("side must be buy or sell")
    if qty <= 0:
        raise ValueError("qty must be positive")
    order_type = (order_type or "market").lower()

    doc = get_account(account_id)
    market = latest_quote(symbol)

    # Conditional / multi-leg orders are always parked for ``match_pending_orders``.
    if order_type in {"stop", "stop_limit", "trailing_stop", "oco"}:
        result = _place_conditional(
            doc, symbol, side, qty, order_type, limit_price, stop_price,
            trail_amount, trail_percent, reduce_only, oco_group, meta, market,
        )
        _save(doc)
        return result

    if order_type == "limit":
        if limit_price is None:
            raise ValueError("limit order requires limit_price")
        # Naive matching: only fill if limit crosses last price; otherwise park
        # the order as pending for ``match_pending_orders`` to revisit later.
        if (side == "buy" and market > limit_price) or (side == "sell" and market < limit_price):
            order = _make_order(symbol, side, qty, "limit", limit_price,
                                status="pending", meta=meta,
                                limit_price=limit_price, reduce_only=reduce_only)
            doc["orders"].append(order)
            _save(doc)
            return order
        fill_price = limit_price
    else:  # market
        fill_price = market

    notional = _apply_fill(doc, symbol, side, qty, fill_price)

    order = _make_order(symbol, side, qty, order_type, fill_price, status="filled",
                        meta=meta, limit_price=limit_price, reduce_only=reduce_only)
    doc["orders"].append(order)
    doc["trades"].append({
        "ts": order["ts"], "symbol": symbol, "side": side,
        "qty": qty, "price": fill_price, "notional": notional,
        "order_id": order["order_id"], "meta": meta or {},
    })

    # Bracket: a long entry can carry attached take-profit / stop-loss exits that
    # are placed as an OCO pair once the entry fills.
    if side == "buy" and (take_profit is not None or stop_loss is not None):
        _attach_bracket(doc, symbol, qty, fill_price, take_profit, stop_loss,
                        order["order_id"])

    _append_mtm(doc)
    _save(doc)
    return order


def _place_conditional(doc, symbol, side, qty, order_type, limit_price, stop_price,
                       trail_amount, trail_percent, reduce_only, oco_group, meta, market):
    """Create one or two pending conditional orders. Mutates ``doc`` in place."""
    if order_type == "oco":
        if limit_price is None or stop_price is None:
            raise ValueError("oco order requires both limit_price (take-profit) and stop_price (stop-loss)")
        group = oco_group or f"oco_{uuid.uuid4().hex[:8]}"
        tp = _make_order(symbol, side, qty, "limit", limit_price, status="pending",
                         meta=meta, limit_price=limit_price, oco_group=group,
                         reduce_only=True)
        sl = _make_order(symbol, side, qty, "stop", stop_price, status="pending",
                         meta=meta, stop_price=stop_price, oco_group=group,
                         reduce_only=True)
        doc["orders"].extend([tp, sl])
        return {"oco_group": group, "orders": [tp, sl]}

    if order_type in {"stop", "stop_limit"}:
        if stop_price is None:
            raise ValueError(f"{order_type} order requires stop_price")
        if order_type == "stop_limit" and limit_price is None:
            raise ValueError("stop_limit order requires limit_price")
        order = _make_order(symbol, side, qty, order_type, stop_price, status="pending",
                            meta=meta, stop_price=stop_price, limit_price=limit_price,
                            oco_group=oco_group, reduce_only=reduce_only)
        doc["orders"].append(order)
        return order

    # trailing_stop
    if trail_amount is None and trail_percent is None:
        raise ValueError("trailing_stop requires trail_amount or trail_percent")
    order = _make_order(symbol, side, qty, "trailing_stop", market, status="pending",
                        meta=meta, trail_amount=trail_amount, trail_percent=trail_percent,
                        trail_ref=market, oco_group=oco_group, reduce_only=reduce_only)
    doc["orders"].append(order)
    return order


def _attach_bracket(doc, symbol, qty, entry_price, take_profit, stop_loss, parent_id):
    """Attach OCO take-profit / stop-loss exits to a freshly filled long entry."""
    group = f"oco_{uuid.uuid4().hex[:8]}"
    base_meta = {"source": "bracket", "parent_order_id": parent_id}
    children = []
    if take_profit is not None:
        children.append(_make_order(
            symbol, "sell", qty, "limit", take_profit, status="pending",
            meta=base_meta, limit_price=take_profit, oco_group=group, reduce_only=True,
        ))
    if stop_loss is not None:
        children.append(_make_order(
            symbol, "sell", qty, "stop", stop_loss, status="pending",
            meta=base_meta, stop_price=stop_loss, oco_group=group, reduce_only=True,
        ))
    doc["orders"].extend(children)
    return children


def _order_fill_price(order: dict, side: str, market: float) -> Optional[float]:
    """Return the fill price if ``order`` triggers at ``market``, else ``None``.

    May mutate ``order`` for trailing stops (high/low water mark + live stop)
    and for stop-limit conversions.
    """
    otype = order.get("order_type", "limit")
    if otype == "limit":
        lp = order.get("limit_price", order.get("price"))
        if lp is None:
            return None
        if (side == "buy" and market <= lp) or (side == "sell" and market >= lp):
            return lp
        return None
    if otype == "stop":
        sp = order.get("stop_price", order.get("price"))
        if sp is None:
            return None
        if (side == "buy" and market >= sp) or (side == "sell" and market <= sp):
            return market
        return None
    if otype == "stop_limit":
        sp = order.get("stop_price")
        lp = order.get("limit_price")
        if sp is None or lp is None:
            return None
        triggered = (side == "buy" and market >= sp) or (side == "sell" and market <= sp)
        if not triggered:
            return None
        if (side == "buy" and market <= lp) or (side == "sell" and market >= lp):
            return lp
        # Triggered but limit not yet crossed: demote to a resting limit order.
        order["order_type"] = "limit"
        order["price"] = lp
        return None
    if otype == "trailing_stop":
        ref = order.get("trail_ref", market)
        amt = order.get("trail_amount")
        pct = order.get("trail_percent")
        if side == "sell":  # protect a long — trail the highs downward
            ref = max(ref, market)
            stop = (ref - amt) if amt is not None else ref * (1 - (pct or 0) / 100.0)
            order["trail_ref"] = ref
            order["stop_price"] = stop
            if market <= stop:
                return market
        else:  # buy trailing — trail the lows upward
            ref = min(ref, market)
            stop = (ref + amt) if amt is not None else ref * (1 + (pct or 0) / 100.0)
            order["trail_ref"] = ref
            order["stop_price"] = stop
            if market >= stop:
                return market
        return None
    return None


def match_pending_orders(account_id: str) -> "list[dict]":
    """Re-evaluate parked conditional orders and fill any that now trigger.

    Supports limit, stop, stop-limit and trailing-stop orders, plus OCO groups
    (when one leg fills the siblings are cancelled). Returns the filled orders.
    """
    doc = get_account(account_id)
    pending = [o for o in doc.get("orders", []) if o.get("status") == "pending"]
    if not pending:
        return []

    filled: list = []
    quote_cache: dict = {}
    cancelled_groups: set = set()

    def _market(sym):
        if sym not in quote_cache:
            quote_cache[sym] = latest_quote(sym)
        return quote_cache[sym]

    for order in pending:
        if order.get("status") != "pending":
            continue
        group = order.get("oco_group")
        if group and group in cancelled_groups:
            continue
        symbol = order["symbol"]
        side = order["side"]
        try:
            market = _market(symbol)
        except Exception:
            continue

        fill_price = _order_fill_price(order, side, market)
        if fill_price is None:
            continue

        try:
            notional = _apply_fill(doc, symbol, side, order["qty"], fill_price)
        except ValueError:
            # Insufficient cash/position now — leave pending for a later pass.
            continue

        order["status"] = "filled"
        order["filled_ts"] = _now_iso()
        order["price"] = fill_price
        doc["trades"].append({
            "ts": order["filled_ts"], "symbol": symbol, "side": side,
            "qty": order["qty"], "price": fill_price, "notional": notional,
            "order_id": order["order_id"], "meta": order.get("meta") or {},
        })
        filled.append(order)
        if group:
            cancelled_groups.add(group)

    # Cancel the surviving legs of any OCO group whose sibling just filled.
    if cancelled_groups:
        for order in doc.get("orders", []):
            if order.get("status") == "pending" and order.get("oco_group") in cancelled_groups:
                order["status"] = "cancelled"
                order["cancelled_ts"] = _now_iso()

    if filled:
        _append_mtm(doc)
    if filled or cancelled_groups:
        _save(doc)
    return filled


def _make_order(symbol, side, qty, order_type, price, status, meta=None, **extra):
    order = {
        "order_id": f"ord_{uuid.uuid4().hex[:10]}",
        "ts": _now_iso(),
        "symbol": symbol,
        "side": side,
        "qty": float(qty),
        "order_type": order_type,
        "price": float(price),
        "status": status,
    }
    for key, value in extra.items():
        if value is not None:
            order[key] = value
    if meta:
        order["meta"] = meta
    return order


def cancel_order(account_id: str, order_id: str) -> dict:
    """Cancel a single pending order (and its OCO siblings, if any)."""
    doc = get_account(account_id)
    target = next((o for o in doc.get("orders", []) if o.get("order_id") == order_id), None)
    if target is None:
        raise FileNotFoundError(order_id)
    if target.get("status") != "pending":
        raise ValueError(f"order {order_id} is not pending (status={target.get('status')})")
    group = target.get("oco_group")
    cancelled = []
    for order in doc.get("orders", []):
        if order.get("status") != "pending":
            continue
        if order.get("order_id") == order_id or (group and order.get("oco_group") == group):
            order["status"] = "cancelled"
            order["cancelled_ts"] = _now_iso()
            cancelled.append(order)
    _save(doc)
    return {"cancelled": [o["order_id"] for o in cancelled]}


def snapshot(account_id: str) -> dict:
    doc = get_account(account_id)
    cash = doc["cash"]
    positions_view = []
    market_value = 0.0
    for sym, p in doc["positions"].items():
        try:
            last = latest_quote(sym)
        except Exception:
            last = p["avg_price"]
        mv = p["qty"] * last
        unreal = (last - p["avg_price"]) * p["qty"]
        positions_view.append({
            "symbol": sym, "qty": p["qty"], "avg_price": p["avg_price"],
            "last_price": last, "market_value": mv, "unrealized_pnl": unreal,
        })
        market_value += mv
    total = cash + market_value
    initial = doc.get("initial_cash", cash)
    return {
        "account_id": account_id,
        "name": doc.get("name"),
        "ccy": doc.get("ccy", "USD"),
        "cash": cash,
        "market_value": market_value,
        "total_equity": total,
        "initial_cash": initial,
        "cumulative_return": (total / initial - 1.0) if initial else 0.0,
        "positions": positions_view,
        "n_orders": len(doc.get("orders", [])),
    }
