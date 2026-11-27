"""Signal-driven automatic order placement for the system-A paper broker.

Turns a fused multi-source signal (:mod:`signal_fusion`) into a concrete
``buy`` / ``sell`` / ``hold`` decision and, when warranted, places a market
order on a paper-trading account via :func:`portfolio.place_order`.

Risk controls (all configurable in :mod:`app.quant.config`):

* score + confidence gates                 — only act on convincing signals
* per-symbol+direction cooldown            — idempotency / anti-churn
* per-order equity cap, confidence-scaled  — bounded position sizing
* cash-reserve floor                       — never fully invest
* sell only reduces an existing long       — no naked shorts in the sim

Design mirrors :class:`PaperExecutionEngine` from the Polymarket lab but
targets the JSON-backed multi-asset accounts.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .. import config
from . import portfolio, signal_fusion

logger = logging.getLogger(__name__)


@dataclass
class AutoTradeDecision:
    symbol: str
    status: str  # "executed" | "skipped" | "blocked"
    reason: Optional[str] = None
    side: Optional[str] = None
    qty: Optional[float] = None
    price: Optional[float] = None
    notional: Optional[float] = None
    score: Optional[float] = None
    confidence: Optional[float] = None
    fingerprint: Optional[str] = None
    order_id: Optional[str] = None
    sources: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def get_or_create_auto_account() -> str:
    """Resolve the dedicated auto-trading account, creating it if needed.

    Resolution order: explicit ``AUTO_TRADE_ACCOUNT_ID`` → existing account
    matching ``AUTO_TRADE_ACCOUNT_NAME`` → freshly created account.
    """
    if config.AUTO_TRADE_ACCOUNT_ID:
        try:
            portfolio.get_account(config.AUTO_TRADE_ACCOUNT_ID)
            return config.AUTO_TRADE_ACCOUNT_ID
        except FileNotFoundError:
            logger.warning(
                "AUTO_TRADE_ACCOUNT_ID %s not found; falling back to name lookup",
                config.AUTO_TRADE_ACCOUNT_ID,
            )

    for acc in portfolio.list_accounts():
        if acc.get("name") == config.AUTO_TRADE_ACCOUNT_NAME:
            return acc["account_id"]

    created = portfolio.create_account(
        name=config.AUTO_TRADE_ACCOUNT_NAME,
        initial_cash=config.AUTO_TRADE_INITIAL_CASH,
    )
    logger.info("created auto-trade account %s", created["account_id"])
    return created["account_id"]


def _fingerprint(symbol: str, direction: str) -> str:
    # One auto trade per symbol+direction per UTC day (cooldown adds finer grain).
    return f"{symbol}:{direction}:{_now().date().isoformat()}"


def _recent_auto_order(doc: dict, fingerprint: str, cooldown_minutes: int) -> bool:
    cutoff = _now() - dt.timedelta(minutes=cooldown_minutes)
    for order in reversed(doc.get("orders", [])):
        meta = order.get("meta") or {}
        if meta.get("source") != "auto_trader":
            continue
        if meta.get("fingerprint") != fingerprint:
            continue
        ts_raw = order.get("ts")
        if not ts_raw:
            return True
        try:
            ts = dt.datetime.fromisoformat(ts_raw)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=dt.timezone.utc)
        except ValueError:
            return True
        if ts >= cutoff:
            return True
    return False


def decide_and_trade(account_id: str, symbol: str) -> AutoTradeDecision:
    """Evaluate ``symbol`` for ``account_id`` and place an order if warranted."""
    fused = signal_fusion.fuse(symbol)
    score = float(fused.get("fused_score") or 0.0)
    confidence = float(fused.get("fused_confidence") or 0.0)
    direction = fused.get("direction", "neutral")
    sources = fused.get("sources", [])

    base = AutoTradeDecision(
        symbol=symbol, status="skipped", side=None,
        score=score, confidence=confidence, sources=sources,
    )

    if not fused.get("ok"):
        base.reason = fused.get("reason", "no signal")
        return base
    if direction == "neutral" or abs(score) < config.AUTO_TRADE_SCORE_THRESHOLD:
        base.reason = f"score {score:.3f} below threshold {config.AUTO_TRADE_SCORE_THRESHOLD}"
        return base
    if confidence < config.AUTO_TRADE_MIN_CONFIDENCE:
        base.reason = f"confidence {confidence:.3f} below min {config.AUTO_TRADE_MIN_CONFIDENCE}"
        return base

    side = "buy" if direction == "up" else "sell"
    fingerprint = _fingerprint(symbol, direction)
    base.fingerprint = fingerprint

    try:
        doc = portfolio.get_account(account_id)
    except FileNotFoundError:
        base.status = "blocked"
        base.reason = "account not found"
        return base

    if _recent_auto_order(doc, fingerprint, config.AUTO_TRADE_COOLDOWN_MINUTES):
        base.reason = "cooldown active for this symbol/direction"
        return base

    try:
        snap = portfolio.snapshot(account_id)
        price = portfolio.latest_quote(symbol)
    except Exception as exc:  # noqa: BLE001
        base.status = "blocked"
        base.reason = f"quote/snapshot failed: {exc}"
        return base

    if price <= 0:
        base.status = "blocked"
        base.reason = "non-positive quote"
        return base

    equity = float(snap.get("total_equity") or 0.0)
    cash = float(snap.get("cash") or 0.0)
    held_qty = next(
        (p["qty"] for p in snap.get("positions", []) if p["symbol"] == symbol),
        0.0,
    )

    # Confidence-scaled target notional, capped by the per-order equity cap.
    target_notional = equity * config.AUTO_TRADE_MAX_POSITION_PCT * confidence

    if side == "buy":
        investable = max(0.0, cash - equity * config.AUTO_TRADE_CASH_RESERVE_PCT)
        target_notional = min(target_notional, investable)
        if target_notional < 1.0:
            base.reason = "insufficient investable cash after reserve"
            return base
        qty = target_notional / price
    else:  # sell — only reduce/flatten an existing long
        if not config.AUTO_TRADE_ALLOW_SELL:
            base.reason = "sell disabled by config"
            return base
        if held_qty <= 0:
            base.reason = "no long position to reduce"
            return base
        qty = min(held_qty, target_notional / price)
        if qty <= 0:
            base.reason = "computed sell qty is zero"
            return base

    meta = {
        "source": "auto_trader",
        "fingerprint": fingerprint,
        "score": round(score, 4),
        "confidence": round(confidence, 4),
        "direction": direction,
        "signal_sources": [s.get("name") for s in sources],
        "decided_at": _now().isoformat(),
    }

    try:
        order = portfolio.place_order(
            account_id=account_id,
            symbol=symbol,
            side=side,
            qty=qty,
            order_type="market",
            meta=meta,
        )
    except ValueError as exc:
        base.status = "blocked"
        base.reason = str(exc)
        return base
    except Exception as exc:  # noqa: BLE001
        logger.exception("auto place_order failed for %s", symbol)
        base.status = "blocked"
        base.reason = str(exc)
        return base

    base.status = "executed"
    base.reason = "order placed"
    base.side = side
    base.qty = float(order.get("qty"))
    base.price = float(order.get("price"))
    base.notional = float(order.get("qty")) * float(order.get("price"))
    base.order_id = order.get("order_id")
    return base


def run_cycle(
    account_id: str,
    watchlist: Optional[List[str]] = None,
    progress_cb: Optional[Any] = None,
) -> Dict[str, Any]:
    """Run one auto-trading pass over ``watchlist`` for ``account_id``.

    Also matches any parked limit orders first so the account reflects fills
    before new sizing decisions are made.

    ``progress_cb(done, total, symbol, decision)`` — if provided — is invoked
    after each symbol so a background task can stream progress to pollers.
    """
    symbols = watchlist if watchlist is not None else config.AUTO_TRADE_WATCHLIST
    total = len(symbols)

    matched: List[dict] = []
    try:
        matched = portfolio.match_pending_orders(account_id)
    except FileNotFoundError:
        return {"account_id": account_id, "error": "account not found", "decisions": []}
    except Exception:  # noqa: BLE001
        logger.exception("match_pending_orders failed for %s", account_id)

    decisions: List[Dict[str, Any]] = []
    for idx, symbol in enumerate(symbols, start=1):
        try:
            decision = decide_and_trade(account_id, symbol)
        except Exception as exc:  # noqa: BLE001
            logger.exception("auto decision failed for %s", symbol)
            decision = AutoTradeDecision(symbol=symbol, status="blocked", reason=str(exc))
        decision_dict = decision.to_dict()
        decisions.append(decision_dict)
        if progress_cb is not None:
            try:
                progress_cb(idx, total, symbol, decision_dict)
            except Exception:  # noqa: BLE001
                logger.debug("progress_cb raised; ignoring", exc_info=True)

    executed = sum(1 for d in decisions if d["status"] == "executed")
    return {
        "account_id": account_id,
        "ts": _now().isoformat(),
        "watchlist": symbols,
        "pending_filled": len(matched),
        "executed": executed,
        "decisions": decisions,
    }
