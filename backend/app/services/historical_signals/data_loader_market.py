"""Historical OHLCV loader.

Primary source: Binance public REST API (`/api/v3/klines`) — no key needed
for spot. Symbols are normalized to USDT pairs (BTC → BTCUSDT). For
non-crypto symbols we try yfinance/FMP daily history, then AkShare for HK
symbols such as 3033.HK.

Cached as JSONL under `<UPLOAD_FOLDER>/backtest/market/<symbol>/<interval>.jsonl`.
Each row: {ts (iso), open, high, low, close, volume}.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests

from ...config import Config

logger = logging.getLogger("finrex.backtest.market")

_BINANCE_BASE = "https://api.binance.com"
_BINANCE_LIMIT = 1000  # max klines per request
_INTERVAL_MS = {
    "1m": 60_000, "5m": 5 * 60_000, "15m": 15 * 60_000, "30m": 30 * 60_000,
    "1h": 60 * 60_000, "4h": 4 * 60 * 60_000, "1d": 24 * 60 * 60_000,
    "1w": 7 * 24 * 60 * 60_000,
}

# Symbols treated as crypto (Binance USDT pair). Anything not here is FMP.
_CRYPTO_SYMBOLS = {"BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX", "MATIC", "DOT"}


def _cache_path(symbol: str, interval: str) -> str:
    base = os.path.join(Config.UPLOAD_FOLDER, "backtest", "market", symbol.upper())
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, f"{interval}.jsonl")


def _to_binance_pair(symbol: str) -> str:
    s = symbol.upper()
    if s.endswith("USDT"):
        return s
    return f"{s}USDT"


def _fetch_binance(symbol: str, interval: str, start: datetime, end: datetime) -> List[Dict[str, Any]]:
    pair = _to_binance_pair(symbol)
    step = _INTERVAL_MS.get(interval)
    if step is None:
        raise ValueError(f"unsupported interval {interval}")
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    out: List[Dict[str, Any]] = []
    cursor = start_ms
    while cursor < end_ms:
        params = {
            "symbol": pair,
            "interval": interval,
            "startTime": cursor,
            "endTime": end_ms,
            "limit": _BINANCE_LIMIT,
        }
        try:
            resp = requests.get(f"{_BINANCE_BASE}/api/v3/klines", params=params, timeout=15)
            resp.raise_for_status()
            rows = resp.json()
        except Exception as exc:
            logger.warning("Binance klines fetch failed pair=%s err=%s", pair, exc)
            break
        if not rows:
            break
        for r in rows:
            ts = datetime.fromtimestamp(r[0] / 1000, tz=timezone.utc)
            out.append({
                "ts": ts.isoformat(),
                "open": float(r[1]),
                "high": float(r[2]),
                "low": float(r[3]),
                "close": float(r[4]),
                "volume": float(r[5]),
            })
        next_cursor = rows[-1][0] + step
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        if len(rows) < _BINANCE_LIMIT:
            break
    return out


def _fetch_fmp_daily(symbol: str, start: datetime, end: datetime) -> List[Dict[str, Any]]:
    if not Config.FMP_API_KEY:
        return []
    url = f"{Config.FMP_BASE_URL.rstrip('/')}/historical-price-eod/full"
    params = {
        "symbol": symbol.upper(),
        "from": start.strftime("%Y-%m-%d"),
        "to": end.strftime("%Y-%m-%d"),
        "apikey": Config.FMP_API_KEY,
    }
    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.warning("FMP daily fetch failed symbol=%s err=%s", symbol, exc)
        return []
    rows = payload.get("historical") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []
    out: List[Dict[str, Any]] = []
    for r in rows:
        date = r.get("date")
        if not date:
            continue
        try:
            ts = datetime.fromisoformat(str(date)).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        out.append({
            "ts": ts.isoformat(),
            "open": float(r.get("open") or 0),
            "high": float(r.get("high") or 0),
            "low": float(r.get("low") or 0),
            "close": float(r.get("close") or 0),
            "volume": float(r.get("volume") or 0),
        })
    out.sort(key=lambda x: x["ts"])
    return out


def _row_from_ohlcv(date_value: Any, open_v: Any, high_v: Any, low_v: Any, close_v: Any, volume_v: Any = 0) -> Dict[str, Any] | None:
    try:
        ts = datetime.fromisoformat(str(date_value).split(" ")[0]).replace(tzinfo=timezone.utc)
    except Exception:
        try:
            import pandas as pd
            ts = pd.Timestamp(date_value).to_pydatetime()
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            else:
                ts = ts.astimezone(timezone.utc)
        except Exception:
            return None
    try:
        row = {
            "ts": ts.isoformat(),
            "open": float(open_v),
            "high": float(high_v),
            "low": float(low_v),
            "close": float(close_v),
            "volume": float(volume_v or 0),
        }
    except (TypeError, ValueError):
        return None
    if row["open"] <= 0 or row["high"] <= 0 or row["low"] <= 0 or row["close"] <= 0:
        return None
    return row


def _fetch_yfinance_daily(symbol: str, start: datetime, end: datetime) -> List[Dict[str, Any]]:
    if not symbol.upper().endswith((".HK", ".SI")) and "." not in symbol:
        return []
    try:
        import pandas as pd
        import yfinance as yf
    except Exception as exc:  # noqa: BLE001
        logger.info("yfinance unavailable for backtest symbol=%s err=%s", symbol, exc)
        return []

    try:
        df = yf.download(
            symbol.upper(),
            start=start.strftime("%Y-%m-%d"),
            end=(end + timedelta(days=1)).strftime("%Y-%m-%d"),
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("yfinance daily fetch failed symbol=%s err=%s", symbol, exc)
        return []
    if df is None or df.empty:
        return []
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=lambda c: str(c).strip().lower().replace(" ", "_"))
    out: List[Dict[str, Any]] = []
    for idx, row in df.iterrows():
        normalized = _row_from_ohlcv(
            idx,
            row.get("open"),
            row.get("high"),
            row.get("low"),
            row.get("close"),
            row.get("volume", 0),
        )
        if normalized:
            out.append(normalized)
    out.sort(key=lambda x: x["ts"])
    return [r for r in out if start.isoformat() <= r["ts"] <= end.isoformat()]


def _hk_symbol(symbol: str) -> str:
    digits = "".join(ch for ch in symbol.split(".")[0] if ch.isdigit())
    return digits.zfill(5) if digits else symbol.split(".")[0]


def _normalize_akshare_rows(df, start: datetime, end: datetime) -> List[Dict[str, Any]]:
    if df is None or getattr(df, "empty", True):
        return []
    col_map = {
        "日期": "ts", "date": "ts", "时间": "ts",
        "开盘": "open", "open": "open",
        "最高": "high", "high": "high",
        "最低": "low", "low": "low",
        "收盘": "close", "close": "close",
        "成交量": "volume", "volume": "volume", "成交额": "turnover",
    }
    renamed = df.rename(columns=lambda c: col_map.get(str(c).strip(), str(c).strip().lower()))
    required = {"ts", "open", "high", "low", "close"}
    if not required.issubset(set(renamed.columns)):
        logger.warning("AkShare HK rows missing OHLC columns: %s", list(df.columns))
        return []
    out: List[Dict[str, Any]] = []
    for _, row in renamed.iterrows():
        normalized = _row_from_ohlcv(
            row.get("ts"),
            row.get("open"),
            row.get("high"),
            row.get("low"),
            row.get("close"),
            row.get("volume", 0),
        )
        if normalized:
            out.append(normalized)
    out.sort(key=lambda x: x["ts"])
    return [r for r in out if start.isoformat() <= r["ts"] <= end.isoformat()]


def _fetch_akshare_hk_daily(symbol: str, start: datetime, end: datetime) -> List[Dict[str, Any]]:
    if not symbol.upper().endswith(".HK"):
        return []
    try:
        import akshare as ak
    except Exception as exc:  # noqa: BLE001
        logger.info("akshare unavailable for backtest symbol=%s err=%s", symbol, exc)
        return []

    hk_symbol = _hk_symbol(symbol.upper())
    start_date = start.strftime("%Y%m%d")
    end_date = end.strftime("%Y%m%d")
    attempts = []
    stock_hk_hist = getattr(ak, "stock_hk_hist", None)
    if callable(stock_hk_hist):
        attempts.append(lambda: stock_hk_hist(symbol=hk_symbol, period="daily", start_date=start_date, end_date=end_date, adjust=""))
    attempts.append(lambda: ak.stock_hk_daily(symbol=hk_symbol, adjust=""))
    fund_etf_hist = getattr(ak, "fund_etf_hist_em", None)
    if callable(fund_etf_hist):
        attempts.append(lambda: fund_etf_hist(symbol=hk_symbol.lstrip("0") or hk_symbol, period="daily", start_date=start_date, end_date=end_date, adjust=""))

    for attempt in attempts:
        try:
            rows = _normalize_akshare_rows(attempt(), start, end)
            if rows:
                return rows
        except Exception as exc:  # noqa: BLE001
            logger.warning("AkShare HK daily fetch attempt failed symbol=%s err=%s", symbol, exc)
    return []


def fetch_ohlcv(
    symbol: str,
    interval: str,
    start: datetime,
    end: datetime,
    *,
    use_cache: bool = True,
) -> List[Dict[str, Any]]:
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    cache = _cache_path(symbol, interval)
    cached: List[Dict[str, Any]] = []
    if use_cache and os.path.exists(cache):
        with open(cache, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    cached.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        in_window = [c for c in cached if start.isoformat() <= c["ts"] <= end.isoformat()]
        if in_window and _covers_window(in_window, interval, start, end):
            return in_window

    if symbol.upper().rstrip("USDT") in _CRYPTO_SYMBOLS or symbol.upper().endswith("USDT"):
        rows = _fetch_binance(symbol, interval, start, end)
    else:
        rows = _fetch_yfinance_daily(symbol, start, end) if interval == "1d" else []
        if not rows:
            rows = _fetch_fmp_daily(symbol, start, end)
        if not rows and interval == "1d":
            rows = _fetch_akshare_hk_daily(symbol, start, end)

    if rows:
        merged = {row["ts"]: row for row in cached}
        for row in rows:
            merged[row["ts"]] = row
        sorted_rows = sorted(merged.values(), key=lambda x: x["ts"])
        with open(cache, "w", encoding="utf-8") as f:
            for row in sorted_rows:
                f.write(json.dumps(row) + "\n")

    return [r for r in rows if start.isoformat() <= r["ts"] <= end.isoformat()]


def _covers_window(rows: List[Dict[str, Any]], interval: str, start: datetime, end: datetime) -> bool:
    """Return cached rows only when they cover the requested window.

    The market desks can switch from 7D/2M to 1Y. A partial cache should not
    satisfy the longer request, otherwise the chart looks like it only has a few
    days of data.
    """
    if not rows:
        return False
    sorted_rows = sorted(rows, key=lambda r: r.get("ts") or "")
    first = _parse_cached_ts(sorted_rows[0].get("ts"))
    last = _parse_cached_ts(sorted_rows[-1].get("ts"))
    if not first or not last:
        return False
    step_ms = _INTERVAL_MS.get(interval, 24 * 60 * 60_000)
    tolerance = timedelta(milliseconds=step_ms * 2)
    return first <= start + tolerance and last >= end - tolerance


def _parse_cached_ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
