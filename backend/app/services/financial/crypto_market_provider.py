"""Crypto market data provider for directional forecasts.

Primary source is Binance public market data. yfinance remains a fallback so
the financial report can still produce a technical view if Binance is blocked.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

from ...config import Config
from ..asset_forecast.market_data import MarketDataService

logger = logging.getLogger("finrex.financial.crypto_market_provider")

BINANCE_SPOT_BASE = "https://api.binance.com"
BINANCE_FUTURES_BASE = "https://fapi.binance.com"
CACHE_DIR = os.path.join(Config.UPLOAD_FOLDER, "crypto_market_cache")
DEFAULT_TTL_MINUTES = 10
DEFAULT_LOOKBACK_LIMIT = 180


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _ensure_cache_dir() -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)


def _cache_path(pair: str) -> str:
    safe = pair.replace("/", "_").replace(":", "_")
    return os.path.join(CACHE_DIR, f"{safe}.json")


def _read_cache(pair: str, ttl_minutes: int) -> Optional[Dict[str, Any]]:
    path = _cache_path(pair)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        fetched_at = payload.get("fetched_at")
        if not fetched_at:
            return None
        ts = datetime.fromisoformat(fetched_at)
        if datetime.now() - ts <= timedelta(minutes=ttl_minutes):
            return payload
    except Exception as exc:  # noqa: BLE001
        logger.warning("crypto cache read failed for %s: %s", pair, exc)
    return None


def _write_cache(pair: str, payload: Dict[str, Any]) -> None:
    _ensure_cache_dir()
    try:
        with open(_cache_path(pair), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("crypto cache write failed for %s: %s", pair, exc)


def normalize_crypto_symbol(symbol: str) -> Dict[str, str]:
    """Normalize BTC / BTCUSDT / BTC-USD / BTC/USDT into Binance + Yahoo ids."""
    raw = (symbol or "BTC").strip().upper()
    if not raw:
        raw = "BTC"
    cleaned = raw.replace(" ", "")
    if "/" in cleaned:
        base, quote = cleaned.split("/", 1)
        quote = quote or "USDT"
    elif "-" in cleaned:
        base, quote = cleaned.split("-", 1)
        quote = "USDT" if quote in {"USD", "USDT"} else quote
    elif cleaned.endswith("USDT") and len(cleaned) > 4:
        base = cleaned[:-4]
        quote = "USDT"
    elif cleaned.endswith("USD") and len(cleaned) > 3:
        base = cleaned[:-3]
        quote = "USDT"
    else:
        base = cleaned
        quote = "USDT"
    base = "BTC" if base in {"XBT", "BITCOIN"} else base
    pair = f"{base}{quote}"
    yahoo = f"{base}-USD"
    return {"input": raw, "base": base, "quote": quote, "pair": pair, "yahoo": yahoo}


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _binance_get(path: str, params: Dict[str, Any], timeout: int = 10, futures: bool = False) -> Any:
    base = BINANCE_FUTURES_BASE if futures else BINANCE_SPOT_BASE
    resp = requests.get(f"{base}{path}", params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _normalize_kline(row: List[Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(row, list) or len(row) < 6:
        return None
    try:
        ts = int(row[0]) / 1000
        return {
            "date": datetime.fromtimestamp(ts).strftime("%Y-%m-%d"),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
        }
    except Exception:
        return None


def _download_binance_ohlcv(pair: str, interval: str, limit: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    status: Dict[str, Any] = {"ok": False, "source": "binance", "error": None, "rows_count": 0}
    try:
        raw = _binance_get("/api/v3/klines", {"symbol": pair, "interval": interval, "limit": limit})
        rows = [item for item in (_normalize_kline(r) for r in raw or []) if item]
        status.update(ok=bool(rows), rows_count=len(rows))
        return rows, status
    except Exception as exc:  # noqa: BLE001
        status["source"] = "binance_error"
        status["error"] = str(exc)
        logger.warning("binance klines failed for %s: %s", pair, exc)
        return [], status


def _fetch_ticker(pair: str) -> Dict[str, Any]:
    try:
        raw = _binance_get("/api/v3/ticker/24hr", {"symbol": pair})
        return {
            "ok": True,
            "source": "binance",
            "last_price": _safe_float(raw.get("lastPrice")),
            "price_change_pct_24h": _safe_float(raw.get("priceChangePercent")),
            "quote_volume_24h": _safe_float(raw.get("quoteVolume")),
            "volume_24h": _safe_float(raw.get("volume")),
            "high_24h": _safe_float(raw.get("highPrice")),
            "low_24h": _safe_float(raw.get("lowPrice")),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "source": "binance_error", "error": str(exc)}


def _fetch_derivatives(pair: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {"ok": False, "source": "binance_futures", "funding": [], "open_interest": None}
    try:
        funding = _binance_get("/fapi/v1/fundingRate", {"symbol": pair, "limit": 8}, futures=True)
        result["funding"] = [
            {
                "funding_rate": _safe_float(item.get("fundingRate")),
                "funding_time": item.get("fundingTime"),
            }
            for item in (funding or [])
            if isinstance(item, dict)
        ]
    except Exception as exc:  # noqa: BLE001
        result["funding_error"] = str(exc)
    try:
        oi = _binance_get("/fapi/v1/openInterest", {"symbol": pair}, futures=True)
        result["open_interest"] = _safe_float(oi.get("openInterest")) if isinstance(oi, dict) else None
    except Exception as exc:  # noqa: BLE001
        result["open_interest_error"] = str(exc)
    result["ok"] = bool(result.get("funding") or result.get("open_interest") is not None)
    return result


class CryptoMarketProvider:
    """Fetch crypto OHLCV and auxiliary market facts."""

    @classmethod
    def fetch_market(
        cls,
        symbol: str = "BTC",
        interval: str = "1d",
        limit: int = DEFAULT_LOOKBACK_LIMIT,
        ttl_minutes: int = DEFAULT_TTL_MINUTES,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        normalized = normalize_crypto_symbol(symbol)
        pair = normalized["pair"]
        cached = _read_cache(pair, ttl_minutes) if use_cache else None
        if cached:
            return {**cached, "cache_hit": True}

        rows, market_status = _download_binance_ohlcv(pair, interval, max(90, min(int(limit or 180), 1000)))
        source = market_status.get("source", "binance")
        warnings: List[str] = []
        if not rows:
            warnings.append(f"Binance market data unavailable: {market_status.get('error') or 'empty'}")
            rows, yf_status = MarketDataService.fetch_ohlcv(normalized["yahoo"], lookback_days=max(180, int(limit or 180)))
            source = yf_status.get("source", "yfinance")
            market_status = {**yf_status, "fallback_from": "binance"}
            if not rows:
                warnings.append(f"Fallback yfinance data unavailable for {normalized['yahoo']}")

        ticker = _fetch_ticker(pair) if rows else {"ok": False, "source": "not_requested"}
        derivatives = _fetch_derivatives(pair) if rows else {"ok": False, "source": "not_requested"}
        payload = {
            "ok": bool(rows),
            "symbol": normalized["base"],
            "pair": pair,
            "quote": normalized["quote"],
            "yahoo_symbol": normalized["yahoo"],
            "interval": interval,
            "source": source,
            "fetched_at": _now_iso(),
            "rows_count": len(rows),
            "ohlcv": rows,
            "ticker": ticker,
            "derivatives": derivatives,
            "status": market_status,
            "warnings": warnings,
        }
        if rows:
            _write_cache(pair, payload)
        return payload

