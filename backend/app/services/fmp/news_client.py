"""Unified FMP News & Social-Sentiment client.

Covers the full FMP `stable` news + social-sentiment surface
(https://site.financialmodelingprep.com/developer/docs#news).

All methods return a normalized list of dicts:
    [{id, title, url, image, site, published_at, symbol, text, source_category}, ...]

Disk-cached for 30 min to reduce API spend.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

import requests

from ...config import Config

logger = logging.getLogger("finrex.fmp.news_client")

_DEFAULT_TTL = 30 * 60  # 30 min
_CACHE_DIR = Path(__file__).resolve().parents[3] / "uploads" / "fmp_cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

_BASE = "https://financialmodelingprep.com"


def _api_key() -> Optional[str]:
    return getattr(Config, "FMP_API_KEY", None) or os.environ.get("FMP_API_KEY")


def _cache_key(*parts: Any) -> Path:
    raw = "|".join(str(p) for p in parts)
    h = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return _CACHE_DIR / f"{parts[0]}_{h}.json"


def _read_cache(fp: Path, ttl: int) -> Optional[Any]:
    if not fp.exists():
        return None
    if time.time() - fp.stat().st_mtime > ttl:
        return None
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_cache(fp: Path, data: Any) -> None:
    try:
        fp.write_text(json.dumps(data), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.warning("FMP cache write failed: %s", exc)


def _normalize_news(item: dict, category: str) -> dict:
    title = item.get("title") or item.get("headline") or ""
    text = item.get("text") or item.get("content") or item.get("summary") or ""
    symbol = item.get("symbol") or item.get("ticker") or item.get("symbols") or item.get("tickers") or ""
    tickers = ", ".join(symbol) if isinstance(symbol, list) else str(symbol or "")
    return {
        "id": item.get("id") or hashlib.md5((title + (item.get("url") or "")).encode()).hexdigest()[:12],
        "title": title,
        "url": item.get("url") or item.get("link") or "",
        "image": item.get("image") or item.get("imageUrl") or "",
        "site": item.get("site") or item.get("source") or item.get("publisher") or "",
        "published_at": item.get("publishedDate") or item.get("date") or item.get("published_at") or "",
        "publishedDate": item.get("publishedDate") or item.get("date") or item.get("published_at") or "",
        "date": item.get("publishedDate") or item.get("date") or item.get("published_at") or "",
        "symbol": tickers,
        "tickers": tickers,
        "text": text,
        "content": text,
        "summary": item.get("summary") or text,
        "source_category": category,
    }


def _normalize_sentiment(item: dict) -> dict:
    return {
        "symbol": item.get("symbol") or "",
        "date": item.get("date") or "",
        "stocktwits_posts": item.get("stocktwitsPosts") or item.get("stocktwits_posts") or 0,
        "twitter_posts": item.get("twitterPosts") or item.get("twitter_posts") or 0,
        "stocktwits_comments": item.get("stocktwitsComments") or item.get("stocktwits_comments") or 0,
        "twitter_comments": item.get("twitterComments") or item.get("twitter_comments") or 0,
        "stocktwits_likes": item.get("stocktwitsLikes") or item.get("stocktwits_likes") or 0,
        "twitter_likes": item.get("twitterLikes") or item.get("twitter_likes") or 0,
        "stocktwits_impressions": item.get("stocktwitsImpressions") or 0,
        "twitter_impressions": item.get("twitterImpressions") or 0,
        "stocktwits_sentiment": item.get("stocktwitsSentiment") or item.get("stocktwits_sentiment") or 0.0,
        "twitter_sentiment": item.get("twitterSentiment") or item.get("twitter_sentiment") or 0.0,
        "rank": item.get("rank"),
        "name": item.get("name") or item.get("companyName") or "",
    }


class FMPNewsClient:
    """Thin requests-based client for FMP news + social-sentiment endpoints."""

    def __init__(self, api_key: Optional[str] = None, timeout: int = 12, ttl: int = _DEFAULT_TTL):
        self.api_key = api_key or _api_key()
        self.timeout = timeout
        self.ttl = ttl

    # ---------- internal HTTP ----------

    def _request(self, path: str, params: dict, cache_tag: str) -> list[dict]:
        if not self.api_key:
            raise RuntimeError("FMP_API_KEY missing")
        full_params = dict(params)
        full_params["apikey"] = self.api_key
        url = f"{_BASE}{path}"
        cache_fp = _cache_key(cache_tag, path, json.dumps(params, sort_keys=True, default=str))
        cached = _read_cache(cache_fp, self.ttl)
        if cached is not None:
            return cached
        try:
            resp = requests.get(url, params=full_params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                # FMP wraps some endpoints as {data: [...]} or single object
                data = data.get("data") or [data]
            if not isinstance(data, list):
                data = []
            _write_cache(cache_fp, data)
            return data
        except requests.RequestException as exc:
            logger.warning("FMP request failed %s: %s", path, exc)
            raise

    # ---------- news endpoints ----------

    def fmp_articles(self, page: int = 0, size: int = 20) -> list[dict]:
        data = self._request("/stable/fmp-articles", {"page": page, "size": size}, "fmp_articles")
        return [_normalize_news(x, "fmp_articles") for x in data]

    def news_general(self, page: int = 0, limit: int = 50, from_: str | None = None, to: str | None = None) -> list[dict]:
        params: dict[str, Any] = {"page": page, "limit": limit}
        if from_: params["from"] = from_
        if to: params["to"] = to
        data = self._request("/stable/news/general-latest", params, "news_general")
        # fallback to non-latest if empty
        if not data:
            data = self._request("/stable/news/general", params, "news_general_alt")
        return [_normalize_news(x, "general") for x in data]

    def news_stock(self, tickers: str | None = None, page: int = 0, limit: int = 50,
                   from_: str | None = None, to: str | None = None) -> list[dict]:
        if not tickers:
            return self.news_stock_latest(page=page, limit=limit)
        params: dict[str, Any] = {"page": page, "limit": limit}
        if tickers: params["symbols"] = tickers
        if from_: params["from"] = from_
        if to: params["to"] = to
        data = self._request("/stable/news/stock", params, "news_stock")
        return [_normalize_news(x, "stock") for x in data]

    def news_stock_latest(self, page: int = 0, limit: int = 50) -> list[dict]:
        data = self._request("/stable/news/stock-latest", {"page": page, "limit": limit}, "news_stock_latest")
        return [_normalize_news(x, "stock_latest") for x in data]

    def news_crypto(self, symbols: str | None = None, page: int = 0, limit: int = 50,
                    from_: str | None = None, to: str | None = None) -> list[dict]:
        params: dict[str, Any] = {"page": page, "limit": limit}
        if symbols: params["symbols"] = symbols
        if from_: params["from"] = from_
        if to: params["to"] = to
        data = self._request("/stable/news/crypto", params, "news_crypto")
        return [_normalize_news(x, "crypto") for x in data]

    def news_crypto_latest(self, page: int = 0, limit: int = 50) -> list[dict]:
        data = self._request("/stable/news/crypto-latest", {"page": page, "limit": limit}, "news_crypto_latest")
        return [_normalize_news(x, "crypto_latest") for x in data]

    def news_forex(self, symbols: str | None = None, page: int = 0, limit: int = 50,
                   from_: str | None = None, to: str | None = None) -> list[dict]:
        params: dict[str, Any] = {"page": page, "limit": limit}
        if symbols: params["symbols"] = symbols
        if from_: params["from"] = from_
        if to: params["to"] = to
        data = self._request("/stable/news/forex", params, "news_forex")
        return [_normalize_news(x, "forex") for x in data]

    def news_forex_latest(self, page: int = 0, limit: int = 50) -> list[dict]:
        data = self._request("/stable/news/forex-latest", {"page": page, "limit": limit}, "news_forex_latest")
        return [_normalize_news(x, "forex_latest") for x in data]

    def news_press_releases(self, symbols: str | None = None, page: int = 0, limit: int = 50,
                            from_: str | None = None, to: str | None = None) -> list[dict]:
        params: dict[str, Any] = {"page": page, "limit": limit}
        if symbols: params["symbols"] = symbols
        if from_: params["from"] = from_
        if to: params["to"] = to
        data = self._request("/stable/news/press-releases", params, "press_releases")
        return [_normalize_news(x, "press_releases") for x in data]

    def news_press_releases_latest(self, page: int = 0, limit: int = 50) -> list[dict]:
        data = self._request("/stable/news/press-releases-latest",
                             {"page": page, "limit": limit}, "press_releases_latest")
        return [_normalize_news(x, "press_releases_latest") for x in data]

    def news_search(self, query: str, page: int = 0, limit: int = 30,
                    from_: str | None = None, to: str | None = None) -> list[dict]:
        params: dict[str, Any] = {"query": query, "page": page, "limit": limit}
        if from_: params["from"] = from_
        if to: params["to"] = to
        data = self._request("/stable/news/search", params, "news_search")
        return [_normalize_news(x, "search") for x in data]

    def articles(self, page: int = 0, size: int = 20) -> list[dict]:
        """Independent /stable/articles endpoint (distinct from fmp-articles)."""
        data = self._request("/stable/articles", {"page": page, "size": size}, "articles")
        return [_normalize_news(x, "articles") for x in data]

    # ---------- social sentiment ----------

    def historical_social_sentiment(self, symbol: str, page: int = 0) -> list[dict]:
        if not symbol:
            return []
        data = self._request("/stable/historical-social-sentiment",
                             {"symbol": symbol, "page": page}, "social_hist")
        return [_normalize_sentiment(x) for x in data]

    def social_sentiment_trending(self, type_: str = "bullish", source: str = "stocktwits") -> list[dict]:
        data = self._request("/stable/social-sentiment/trending",
                             {"type": type_, "source": source}, "social_trending")
        return [_normalize_sentiment(x) for x in data]

    def social_sentiment_changes(self, type_: str = "bullish", source: str = "stocktwits") -> list[dict]:
        data = self._request("/stable/social-sentiment/changes",
                             {"type": type_, "source": source}, "social_changes")
        return [_normalize_sentiment(x) for x in data]


# Singleton shared client
_client: Optional[FMPNewsClient] = None


def get_client() -> FMPNewsClient:
    global _client
    if _client is None:
        _client = FMPNewsClient()
    return _client
