"""StockTwits Provider（公开匿名端点）。

为美股标的拉取 StockTwits ``streams/symbol/{ticker}.json`` 的最近消息。

StockTwits 自带 ``entities.sentiment.basic`` 字段（Bullish / Bearish），
作为 ``prior_sentiment`` 直通后续打分，省 LLM token。

- 匿名端点速率约 200 req/h；本地 60s 缓存。
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

import requests

from ...config import Config

logger = logging.getLogger("finrex.financial.stocktwits_provider")

_BASE_URL = "https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json"
_TRENDING_URL = "https://api.stocktwits.com/api/2/streams/trending.json"
_USER_AGENT = "FinRex/0.1 (sentiment-research)"
_CACHE_TTL_SECONDS = 60


def _cache_root() -> str:
    base = getattr(Config, "UPLOAD_ROOT", None) or os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "uploads"
    )
    root = os.path.abspath(os.path.join(base, "stocktwits_cache"))
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
        logger.debug("stocktwits cache write failed: %s", exc)


def _sentiment_from_entities(entities: Any) -> Optional[str]:
    """StockTwits 用户提交时可标记 Bullish/Bearish。"""
    if not isinstance(entities, dict):
        return None
    sentiment = entities.get("sentiment")
    if isinstance(sentiment, dict):
        basic = (sentiment.get("basic") or "").strip().lower()
        if basic in {"bullish", "bearish"}:
            return basic
    return None


def _symbols_from_message(raw: Dict[str, Any]) -> str:
    symbols = raw.get("symbols")
    if not isinstance(symbols, list):
        return ""
    out: List[str] = []
    for item in symbols:
        if not isinstance(item, dict):
            continue
        symbol = (item.get("symbol") or item.get("title") or "").strip().upper()
        if symbol:
            out.append(symbol)
    return ",".join(dict.fromkeys(out))


def _normalize_message(raw: Dict[str, Any], symbol: str = "") -> Dict[str, Any]:
    body = (raw.get("body") or "").strip()
    created = raw.get("created_at") or ""
    user = raw.get("user") or {}
    username = (user.get("username") or "anonymous") if isinstance(user, dict) else "anonymous"
    followers = 0
    if isinstance(user, dict):
        followers = int(user.get("followers") or 0)
    prior = _sentiment_from_entities(raw.get("entities"))
    tickers = symbol.upper() if symbol else _symbols_from_message(raw)
    return {
        "title": body[:80],
        "text": body,
        "url": f"https://stocktwits.com/{username}/message/{raw.get('id')}" if raw.get("id") else "",
        "site": "stocktwits",
        "published_at": created,
        "tickers": tickers,
        "like_count": int(((raw.get("likes") or {}).get("total") or 0)) if isinstance(raw.get("likes"), dict) else 0,
        "reply_count": 0,
        "post_id": str(raw.get("id") or ""),
        "author": username,
        "author_followers": followers,
        "prior_sentiment": prior,  # "bullish" | "bearish" | None
        "text_empty": not body,
        "weight": 1.0 if body else 0.0,
        "source": "stocktwits",
        "source_type": "stocktwits",
    }


class StockTwitsProvider:
    """StockTwits 公开 stream 拉取。"""

    @staticmethod
    def fetch_stream(symbol: str, limit: int = 30, timeout: int = 8, use_cache: bool = True) -> Dict[str, Any]:
        result: Dict[str, Any] = {"ok": False, "items": [], "source": "stocktwits", "error": None}
        sym = (symbol or "").strip().upper()
        cache_key = sym or "__TRENDING__"

        if use_cache:
            cached = _read_cache(cache_key)
            if cached is not None:
                result.update(ok=bool(cached), items=cached[:limit], source="stocktwits_cache")
                return result

        url = _BASE_URL.format(symbol=sym) if sym else _TRENDING_URL
        try:
            resp = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=timeout)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("StockTwits fetch failed for %s: %s", sym, exc)
            result["error"] = str(exc)
            return result

        messages = (payload or {}).get("messages") or []
        items: List[Dict[str, Any]] = []
        for raw in messages:
            if not isinstance(raw, dict):
                continue
            normalized = _normalize_message(raw, sym)
            if normalized["text"]:
                items.append(normalized)

        _write_cache(cache_key, items)
        result.update(ok=bool(items), items=items[:limit], source="stocktwits" if sym else "stocktwits_trending")
        return result
