"""Market data loader for the asset forecast module.

Wraps yfinance with a simple on-disk JSON cache (TTL ~ 1 day) so the
forecast service can be called repeatedly without rate-limiting Yahoo.

Cache file format (per symbol):
    {
        "symbol": "3033.HK",
        "fetched_at": "2026-05-06T08:00:00",
        "rows": [
            {"date": "2026-04-01", "open": 5.12, "high": 5.20,
             "low": 5.05, "close": 5.18, "volume": 1234567},
            ...
        ]
    }

The module degrades gracefully:
- yfinance missing  → returns empty list, ``ok=False``
- network failure   → returns cached data if available, else empty
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from ...config import Config

logger = logging.getLogger("finrex.asset_forecast.market_data")

CACHE_DIR = os.path.join(Config.UPLOAD_FOLDER, "market_cache")
# 180 calendar days ≈ 120 trading days in theory, but yfinance often
# returns only ~60 bars for HK tickers. Use 365d to comfortably exceed
# the 70-bar MIN_BARS threshold of the signal engine.
DEFAULT_LOOKBACK_DAYS = 365
DEFAULT_TTL_HOURS = 24


# ---------------------------------------------------------------------------
# Simple OHLC row container (avoids hard pandas dependency at import time)
# ---------------------------------------------------------------------------


def _ensure_cache_dir() -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)


def _cache_path(symbol: str) -> str:
    safe = symbol.replace("/", "_").replace(":", "_")
    return os.path.join(CACHE_DIR, f"{safe}.json")


def _read_cache(symbol: str) -> Optional[Dict[str, Any]]:
    path = _cache_path(symbol)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("market cache read failed for %s: %s", symbol, exc)
        return None


def _write_cache(symbol: str, payload: Dict[str, Any]) -> None:
    _ensure_cache_dir()
    try:
        with open(_cache_path(symbol), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception as exc:
        logger.warning("market cache write failed for %s: %s", symbol, exc)


def _is_fresh(payload: Dict[str, Any], ttl_hours: int) -> bool:
    fetched_at = payload.get("fetched_at")
    if not fetched_at:
        return False
    try:
        ts = datetime.fromisoformat(fetched_at)
    except ValueError:
        return False
    return datetime.now() - ts < timedelta(hours=ttl_hours)


# ---------------------------------------------------------------------------


def _download_yfinance(symbol: str, lookback_days: int) -> List[Dict[str, Any]]:
    try:
        import yfinance as yf  # type: ignore
    except ImportError:
        logger.warning("yfinance not installed; cannot fetch %s", symbol)
        return []

    period = f"{max(lookback_days, 30)}d"
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval="1d", auto_adjust=False)
    except Exception as exc:
        logger.warning("yfinance download failed for %s: %s", symbol, exc)
        return []

    if df is None or df.empty:
        logger.info("yfinance returned empty frame for %s", symbol)
        return []

    rows: List[Dict[str, Any]] = []
    for idx, row in df.iterrows():
        try:
            rows.append({
                "date": idx.strftime("%Y-%m-%d"),
                "open": float(row.get("Open", 0.0) or 0.0),
                "high": float(row.get("High", 0.0) or 0.0),
                "low": float(row.get("Low", 0.0) or 0.0),
                "close": float(row.get("Close", 0.0) or 0.0),
                "volume": float(row.get("Volume", 0.0) or 0.0),
            })
        except Exception:
            continue
    return rows


# ---------------------------------------------------------------------------


class MarketDataService:
    """Public façade for fetching daily OHLCV with disk caching."""

    @staticmethod
    def fetch_ohlcv(
        symbol: str,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        ttl_hours: int = DEFAULT_TTL_HOURS,
        use_cache: bool = True,
        min_rows: int = 0,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Return ``(rows, status)`` tuple.

        ``status`` keys: ``ok`` (bool), ``source`` (cache|yfinance|empty),
        ``fetched_at``, ``rows_count``, ``symbol``.
        """
        symbol = (symbol or "").strip()
        status: Dict[str, Any] = {
            "symbol": symbol,
            "ok": False,
            "source": "empty",
            "fetched_at": None,
            "rows_count": 0,
            "min_rows": max(0, int(min_rows or 0)),
            "rows_below_min": False,
        }
        if not symbol:
            return [], status

        cached = _read_cache(symbol) if use_cache else None
        cache_rows = (cached.get("rows") or []) if cached else []
        cache_has_min_rows = len(cache_rows) >= status["min_rows"]
        if cached and _is_fresh(cached, ttl_hours) and cache_has_min_rows:
            rows = cached.get("rows") or []
            status.update(ok=bool(rows), source="cache",
                          fetched_at=cached.get("fetched_at"),
                          rows_count=len(rows))
            return rows, status

        rows = _download_yfinance(symbol, lookback_days)
        if rows:
            payload = {
                "symbol": symbol,
                "fetched_at": datetime.now().replace(microsecond=0).isoformat(),
                "rows": rows,
            }
            _write_cache(symbol, payload)
            status.update(ok=True, source="yfinance",
                          fetched_at=payload["fetched_at"],
                          rows_count=len(rows),
                          rows_below_min=len(rows) < status["min_rows"])
            return rows, status

        # Fall back to stale cache rather than returning nothing
        if cached and cached.get("rows"):
            rows = cached["rows"]
            status.update(ok=True, source="stale_cache",
                          fetched_at=cached.get("fetched_at"),
                          rows_count=len(rows),
                          rows_below_min=len(rows) < status["min_rows"])
            return rows, status

        return [], status

    @staticmethod
    def closes(rows: List[Dict[str, Any]]) -> List[float]:
        return [float(r.get("close") or 0.0) for r in rows if r.get("close")]


# ---------------------------------------------------------------------------
# CLI helper: ``python -m app.services.asset_forecast.market_data 3033.HK``
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    import sys

    sym = sys.argv[1] if len(sys.argv) > 1 else "3033.HK"
    lookback = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    rows, status = MarketDataService.fetch_ohlcv(sym, lookback_days=lookback, use_cache=False)
    print(json.dumps({"status": status, "tail": rows[-5:]}, ensure_ascii=False, indent=2))
