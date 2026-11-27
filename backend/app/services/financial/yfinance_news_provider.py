"""yfinance 新闻 Provider。

通过 ``yfinance.Ticker(symbol).news`` 拉取 Yahoo Finance 聚合新闻，
作为 FMP stock_news 不足时的补充。失败时返回空列表 + status。

磁盘缓存 30 分钟，避免重复请求 Yahoo。
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree

import requests

from ...config import Config

logger = logging.getLogger("finrex.financial.yfinance_news_provider")

_CACHE_TTL_SECONDS = 30 * 60  # 30 min
_YAHOO_TOP_STORIES_RSS = "https://finance.yahoo.com/rss/topstories"
_USER_AGENT = "Mozilla/5.0 FinRex/0.1"


def _cache_root() -> str:
    base = getattr(Config, "UPLOAD_ROOT", None) or os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "uploads"
    )
    root = os.path.abspath(os.path.join(base, "yfinance_news_cache"))
    os.makedirs(root, exist_ok=True)
    return root


def _cache_path(symbol: str) -> str:
    safe = symbol.upper().replace("/", "_").replace("\\", "_")
    return os.path.join(_cache_root(), f"{safe}.json")


def _read_cache(symbol: str) -> Optional[List[Dict[str, Any]]]:
    path = _cache_path(symbol)
    if not os.path.exists(path):
        return None
    if (time.time() - os.path.getmtime(path)) > _CACHE_TTL_SECONDS:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def _write_cache(symbol: str, items: List[Dict[str, Any]]) -> None:
    try:
        with open(_cache_path(symbol), "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001
        logger.debug("yfinance cache write failed: %s", exc)


def _normalize_raw(raw: Dict[str, Any]) -> Dict[str, Any]:
    """兼容 yfinance 0.2.40+ 的两种返回结构。"""
    # New schema: {"id":..., "content": {"title", "summary", "pubDate", "canonicalUrl":{"url"}, "provider":{"displayName"}}}
    if "content" in raw and isinstance(raw["content"], dict):
        content = raw["content"]
        title = (content.get("title") or "").strip()
        summary = (content.get("summary") or content.get("description") or "").strip()
        url = ""
        canonical = content.get("canonicalUrl") or {}
        if isinstance(canonical, dict):
            url = canonical.get("url") or ""
        if not url:
            click = content.get("clickThroughUrl") or {}
            if isinstance(click, dict):
                url = click.get("url") or ""
        site = ""
        provider = content.get("provider") or {}
        if isinstance(provider, dict):
            site = provider.get("displayName") or provider.get("url") or "yahoo_finance"
        published = content.get("pubDate") or content.get("displayTime") or ""
    else:
        # Legacy schema flat keys
        title = (raw.get("title") or "").strip()
        summary = (raw.get("summary") or "").strip()
        url = raw.get("link") or raw.get("url") or ""
        site = raw.get("publisher") or "yahoo_finance"
        published = ""
        ts = raw.get("providerPublishTime")
        if isinstance(ts, (int, float)) and ts > 0:
            try:
                published = datetime.utcfromtimestamp(float(ts)).isoformat()
            except (OverflowError, OSError):
                published = ""
    text = summary or title
    return {
        "title": title,
        "text": text,
        "url": url,
        "site": site or "yahoo_finance",
        "published_at": published or "",
        "tickers": "",
        "text_empty": not summary,
        "weight": 1.0 if summary else 0.4,
        "source": "yfinance",
    }


def _normalize_rss_item(raw: ElementTree.Element) -> Dict[str, Any]:
    title = (raw.findtext("title") or "").strip()
    summary = (raw.findtext("description") or "").strip()
    url = (raw.findtext("link") or "").strip()
    published_raw = (raw.findtext("pubDate") or "").strip()
    published = published_raw
    if published_raw:
        try:
            published = parsedate_to_datetime(published_raw).isoformat()
        except (TypeError, ValueError, IndexError, OverflowError):
            published = published_raw
    return {
        "title": title,
        "text": summary or title,
        "url": url,
        "site": "Yahoo Finance",
        "publisher": "Yahoo Finance",
        "published_at": published or "",
        "tickers": "",
        "text_empty": not summary,
        "weight": 1.0 if summary else 0.4,
        "source": "yahoo_finance_topstories",
    }


def _fetch_yahoo_top_stories(limit: int, timeout: int = 8) -> Dict[str, Any]:
    result: Dict[str, Any] = {"ok": False, "items": [], "source": "yahoo_finance_topstories", "error": None}
    try:
        resp = requests.get(_YAHOO_TOP_STORIES_RSS, headers={"User-Agent": _USER_AGENT}, timeout=timeout)
        resp.raise_for_status()
        root = ElementTree.fromstring(resp.content)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Yahoo Finance top stories fetch failed: %s", exc)
        result["error"] = str(exc)
        return result

    items = [_normalize_rss_item(item) for item in root.findall("./channel/item")]
    items = [it for it in items if it["title"] or it["text"]]
    result.update(ok=bool(items), items=items[:limit])
    return result


class YFinanceNewsProvider:
    """Yahoo Finance 新闻拉取（带磁盘缓存）。"""

    @staticmethod
    def fetch(symbol: str, limit: int = 15, use_cache: bool = True) -> Dict[str, Any]:
        result: Dict[str, Any] = {"ok": False, "items": [], "source": "yfinance", "error": None}
        sym = (symbol or "").strip().upper()
        if not sym:
            cache_key = "__MARKET_TOPSTORIES__"
            if use_cache:
                cached = _read_cache(cache_key)
                if cached is not None:
                    result.update(ok=bool(cached), items=cached[:limit], source="yahoo_finance_topstories_cache")
                    return result
            top_stories = _fetch_yahoo_top_stories(limit=limit)
            if top_stories.get("items"):
                _write_cache(cache_key, top_stories["items"])
            result.update(top_stories)
            return result

        if use_cache:
            cached = _read_cache(sym)
            if cached is not None:
                result.update(ok=bool(cached), items=cached[:limit], source="yfinance_cache")
                return result

        try:
            import yfinance as yf  # type: ignore
        except Exception as exc:  # noqa: BLE001
            result["error"] = f"yfinance not available: {exc}"
            return result

        try:
            ticker = yf.Ticker(sym)
            raw_items = list(getattr(ticker, "news", []) or [])
        except Exception as exc:  # noqa: BLE001
            logger.warning("yfinance news fetch failed for %s: %s", sym, exc)
            result["error"] = str(exc)
            return result

        items = [_normalize_raw(r) for r in raw_items if isinstance(r, dict)]
        items = [it for it in items if it["title"] or it["text"]]
        _write_cache(sym, items)
        result.update(ok=bool(items), items=items[:limit])
        return result
