"""FMP historical news loader shared by backtest, validation, and quant.

Pulls stock news, press releases, and crypto news in `[start, end]` windows
and caches each month as JSONL under
`<UPLOAD_FOLDER>/backtest/sentiment/fmp/<symbol>/<yyyy-mm>.jsonl`.

Network calls are best-effort: if FMP is unreachable, callers still receive
whatever cache exists so the engines can run on prior pulls.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import requests

from ...config import Config

logger = logging.getLogger("finrex.backtest.fmp")

_DEFAULT_TIMEOUT = 15
_PAGE_SIZE = 50


def _parse_ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        ts = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _cache_dir(symbol: str) -> str:
    base = os.path.join(Config.UPLOAD_FOLDER, "backtest", "sentiment", "fmp", symbol.upper())
    os.makedirs(base, exist_ok=True)
    return base


def _cache_path(symbol: str, year_month: str) -> str:
    return os.path.join(_cache_dir(symbol), f"{year_month}.jsonl")


def _coerce_cached(item: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(item)
    item.setdefault("source", "fmp")
    item.setdefault("source_type", "news")
    item.setdefault("raw_symbol", item.get("symbol") or item.get("tickers") or "")
    item.setdefault("symbol", item.get("raw_symbol") or "")
    return item


def _read_cache(symbol: str, year_month: str) -> List[Dict[str, Any]]:
    path = _cache_path(symbol, year_month)
    if not os.path.exists(path):
        return []
    out: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                out.append(_coerce_cached(item))
    return out


def _write_cache(symbol: str, year_month: str, items: Iterable[Dict[str, Any]]) -> None:
    path = _cache_path(symbol, year_month)
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def _months_between(start: datetime, end: datetime) -> List[str]:
    months: List[str] = []
    cur = datetime(start.year, start.month, 1, tzinfo=timezone.utc)
    last = datetime(end.year, end.month, 1, tzinfo=timezone.utc)
    while cur <= last:
        months.append(cur.strftime("%Y-%m"))
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)
    return months


def _endpoint_url(endpoint: str) -> str:
    base = Config.FMP_BASE_URL.rstrip("/")
    path = endpoint.lstrip("/")
    if base.endswith("/stable") and path.startswith("stable/"):
        path = path[len("stable/"):]
    return f"{base}/{path}"


def _fetch_endpoint(endpoint: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not Config.FMP_API_KEY:
        raise RuntimeError("FMP_API_KEY missing")
    url = _endpoint_url(endpoint)
    full_params = dict(params)
    full_params["apikey"] = Config.FMP_API_KEY
    resp = requests.get(url, params=full_params, timeout=_DEFAULT_TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()
    return payload if isinstance(payload, list) else []


def _normalize(
    item: Dict[str, Any],
    *,
    source_type: str,
    requested_symbol: str,
) -> Optional[Dict[str, Any]]:
    """Normalize FMP article rows to a single shape used by the engines."""
    text = item.get("text") or item.get("content") or item.get("title") or ""
    title = item.get("title") or ""
    publish = item.get("publishedDate") or item.get("date") or item.get("published")
    if not text and not title:
        return None
    raw_symbol = item.get("symbol") or item.get("symbols") or item.get("tickers") or requested_symbol
    return {
        "source": "fmp",
        "source_type": source_type,
        "symbol": requested_symbol,
        "raw_symbol": raw_symbol,
        "title": title,
        "text": text,
        "site": item.get("site") or item.get("publisher") or item.get("source") or "",
        "url": item.get("url") or item.get("link") or "",
        "published_at": publish,
    }


def _is_in_window(item: Dict[str, Any], start: datetime, end: datetime) -> bool:
    ts = _parse_ts(item.get("published_at"))
    return bool(ts and start <= ts <= end)


def _dedupe(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for item in items:
        key = (
            item.get("source_type"),
            item.get("url") or "",
            item.get("title") or "",
            item.get("published_at") or "",
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _symbol_variants(symbol: str) -> List[str]:
    raw = (symbol or "").strip().upper()
    if not raw:
        return []
    variants: List[str] = []

    def add(value: str) -> None:
        value = value.strip().upper()
        if value and value not in variants:
            variants.append(value)

    add(raw)
    add(raw.replace("/", "").replace("-", ""))
    if "-" in raw or "/" in raw:
        sep = "-" if "-" in raw else "/"
        base, _, quote = raw.partition(sep)
        if quote in {"USDT", "USD", "USDC"}:
            add(f"{base}USD")
            add(f"{base}USDT")
            add(base)
    if raw.endswith(".HK"):
        base = raw[:-3]
        add(base)
        if base.isdigit():
            add(base.zfill(5))
            add(f"{base.zfill(5)}.HK")
    if raw.endswith((".SH", ".SZ")):
        base, suffix = raw.split(".", 1)
        add(base)
        add(f"{suffix}{base}")
    return variants


def _endpoint_specs(symbol: str) -> List[Dict[str, Any]]:
    variants = _symbol_variants(symbol)
    is_crypto = "-" in symbol or "/" in symbol
    specs: List[Dict[str, Any]] = []
    if is_crypto:
        for variant in variants:
            specs.append({
                "endpoint": "news/crypto",
                "params": {"symbols": variant},
                "source_type": "crypto_news",
            })
        return specs
    for variant in variants:
        specs.append({
            "endpoint": "news/stock",
            "params": {"symbols": variant},
            "source_type": "stock_news",
        })
        specs.append({
            "endpoint": "news/press-releases",
            "params": {"symbols": variant},
            "source_type": "press_release",
        })
    return specs


def fetch_window_with_coverage(
    symbol: str,
    start: datetime,
    end: datetime,
    *,
    use_cache: bool = True,
    max_pages: int = 40,
) -> Dict[str, Any]:
    items, meta = _fetch_window_internal(
        symbol,
        start,
        end,
        use_cache=use_cache,
        max_pages=max_pages,
    )
    by_type: Dict[str, int] = {}
    for item in items:
        source_type = str(item.get("source_type") or "news")
        by_type[source_type] = by_type.get(source_type, 0) + 1
    return {
        "items": items,
        "coverage": {
            **meta,
            "source": "fmp",
            "available": bool(items),
            "article_count": len(items),
            "source_type_counts": by_type,
            "symbol_variants": _symbol_variants(symbol),
        },
    }


def fetch_window(
    symbol: str,
    start: datetime,
    end: datetime,
    *,
    use_cache: bool = True,
    max_pages: int = 40,
) -> List[Dict[str, Any]]:
    return _fetch_window_internal(symbol, start, end, use_cache=use_cache, max_pages=max_pages)[0]


def _fetch_window_internal(
    symbol: str,
    start: datetime,
    end: datetime,
    *,
    use_cache: bool = True,
    max_pages: int = 40,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Return all FMP articles for `symbol` within `[start, end]`."""
    start = _ensure_utc(start)
    end = _ensure_utc(end)

    months = _months_between(start, end)
    specs = _endpoint_specs(symbol)
    meta: Dict[str, Any] = {
        "cache_hit": False,
        "endpoint_family": sorted({s["endpoint"] for s in specs}),
        "endpoint_specs": [
            {"endpoint": s["endpoint"], "symbols": s.get("params", {}).get("symbols"), "source_type": s["source_type"]}
            for s in specs
        ],
        "symbol_variants": _symbol_variants(symbol),
        "fallback_reason": None,
        "errors": [],
    }
    cached: List[Dict[str, Any]] = []
    if use_cache:
        for ym in months:
            cached.extend(_read_cache(symbol, ym))

    if cached:
        in_window = [c for c in cached if _is_in_window(c, start, end)]
        if in_window:
            logger.info("FMP cache hit symbol=%s items=%d", symbol, len(in_window))
            out = _dedupe(in_window)
            meta["cache_hit"] = True
            return out, meta

    collected: List[Dict[str, Any]] = []
    for spec in specs:
        endpoint = spec["endpoint"]
        base_params = dict(spec["params"])
        for page in range(max_pages):
            try:
                params = dict(base_params)
                params.update({"page": page, "limit": _PAGE_SIZE})
                rows = _fetch_endpoint(endpoint, params)
            except Exception as exc:
                logger.warning("FMP fetch failed endpoint=%s page=%d err=%s", endpoint, page, exc)
                meta["errors"].append(f"{endpoint}:{base_params.get('symbols')}:{exc}")
                break
            if not rows:
                break
            for row in rows:
                row = dict(row)
                row["_fmp_source_type"] = spec["source_type"]
                row["_fmp_requested_symbol"] = base_params.get("symbols") or symbol
                collected.append(row)
            try:
                last = rows[-1]
                last_date = _parse_ts(last.get("publishedDate") or last.get("date"))
                if last_date and last_date < start:
                    break
            except Exception:
                pass

    normalized: List[Dict[str, Any]] = []
    for raw in collected:
        n = _normalize(
            raw,
            source_type=str(raw.get("_fmp_source_type") or "news"),
            requested_symbol=str(raw.get("_fmp_requested_symbol") or symbol),
        )
        if n is not None:
            normalized.append(n)
    normalized = _dedupe(normalized)

    by_month: Dict[str, List[Dict[str, Any]]] = {ym: [] for ym in months}
    for item in normalized:
        if not _is_in_window(item, start, end):
            continue
        ts = _parse_ts(item.get("published_at"))
        if ts is None:
            continue
        ym = ts.strftime("%Y-%m")
        by_month.setdefault(ym, []).append(item)
    for ym, items in by_month.items():
        if items:
            _write_cache(symbol, ym, items)

    out = [item for items in by_month.values() for item in items]
    if not out:
        if meta["errors"]:
            meta["fallback_reason"] = "fmp_fetch_failed_or_unavailable"
        else:
            meta["fallback_reason"] = "no_fmp_articles_in_window"
    return out, meta
