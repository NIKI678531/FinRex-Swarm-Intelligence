"""Read-only Binance public REST market data for the BTC desks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import requests

from ..historical_signals import data_loader_market


BINANCE_BASE = "https://api.binance.com"
PAIR = "BTCUSDT"
SYMBOL = "BTC"
ALLOWED_INTERVALS = {"1m", "5m", "15m", "1h", "4h", "1d"}
LOOKBACKS = {
    "1d": timedelta(days=1),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "60d": timedelta(days=60),
    "2m": timedelta(days=60),
    "180d": timedelta(days=180),
    "6m": timedelta(days=180),
    "365d": timedelta(days=365),
    "1y": timedelta(days=365),
    "12m": timedelta(days=365),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_interval(interval: str) -> str:
    value = (interval or "1h").strip()
    if value not in ALLOWED_INTERVALS:
        raise ValueError(f"unsupported interval {value}; allowed={sorted(ALLOWED_INTERVALS)}")
    return value


def _parse_lookback(lookback: str) -> timedelta:
    value = (lookback or "7d").strip().lower()
    if value not in LOOKBACKS:
        raise ValueError(f"unsupported lookback {value}; allowed={sorted(LOOKBACKS)}")
    return LOOKBACKS[value]


def ohlcv(interval: str = "1h", lookback: str = "7d") -> Dict[str, Any]:
    parsed_interval = _parse_interval(interval)
    delta = _parse_lookback(lookback)
    end = _utcnow()
    start = end - delta
    rows = data_loader_market.fetch_ohlcv(SYMBOL, parsed_interval, start, end)
    return {
        "symbol": SYMBOL,
        "pair": PAIR,
        "interval": parsed_interval,
        "lookback": lookback,
        "rows": rows,
        "source": "binance_public_rest",
        "ts": end.isoformat(),
    }


def ticker() -> Dict[str, Any]:
    resp = requests.get(f"{BINANCE_BASE}/api/v3/ticker/24hr", params={"symbol": PAIR}, timeout=10)
    resp.raise_for_status()
    data = resp.json() or {}
    return {
        "symbol": SYMBOL,
        "pair": PAIR,
        "last": _float(data.get("lastPrice")),
        "change_pct_24h": _float(data.get("priceChangePercent")) / 100.0,
        "high_24h": _float(data.get("highPrice")),
        "low_24h": _float(data.get("lowPrice")),
        "volume_24h": _float(data.get("volume")),
        "quote_volume_24h": _float(data.get("quoteVolume")),
        "ts": datetime.fromtimestamp((_int(data.get("closeTime")) or int(_utcnow().timestamp() * 1000)) / 1000, tz=timezone.utc).isoformat(),
        "source": "binance_public_rest",
    }


def depth(limit: int = 20) -> Dict[str, Any]:
    safe_limit = min(max(int(limit or 20), 5), 100)
    resp = requests.get(f"{BINANCE_BASE}/api/v3/depth", params={"symbol": PAIR, "limit": safe_limit}, timeout=10)
    resp.raise_for_status()
    data = resp.json() or {}
    return {
        "symbol": SYMBOL,
        "pair": PAIR,
        "last_update_id": data.get("lastUpdateId"),
        "bids": [_book_row(row) for row in (data.get("bids") or [])],
        "asks": [_book_row(row) for row in (data.get("asks") or [])],
        "ts": _utcnow().isoformat(),
        "source": "binance_public_rest",
    }


def trades(limit: int = 50) -> Dict[str, Any]:
    safe_limit = min(max(int(limit or 50), 5), 500)
    resp = requests.get(f"{BINANCE_BASE}/api/v3/trades", params={"symbol": PAIR, "limit": safe_limit}, timeout=10)
    resp.raise_for_status()
    data = resp.json() or []
    out: List[Dict[str, Any]] = []
    for row in data:
        price = _float(row.get("price"))
        qty = _float(row.get("qty"))
        out.append({
            "id": row.get("id"),
            "price": price,
            "qty": qty,
            "quote_qty": price * qty,
            "ts": datetime.fromtimestamp((_int(row.get("time")) or int(_utcnow().timestamp() * 1000)) / 1000, tz=timezone.utc).isoformat(),
            "side": "sell" if row.get("isBuyerMaker") else "buy",
        })
    return {"symbol": SYMBOL, "pair": PAIR, "trades": out, "ts": _utcnow().isoformat(), "source": "binance_public_rest"}


def _book_row(row: List[Any]) -> Dict[str, float]:
    price = _float(row[0] if len(row) > 0 else 0)
    qty = _float(row[1] if len(row) > 1 else 0)
    return {"price": price, "qty": qty, "notional": price * qty}


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
