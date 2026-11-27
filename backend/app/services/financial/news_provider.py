"""新闻 / 用户评论 Provider。

报告 B 的"现实层"语料来源：
1. Step1 用户输入的真实评论（保存在 simulation/project metadata 或 reaction run）
2. 关联的 FMP / RSS 实时新闻（针对 symbol 或事件关键词）

设计原则：尽量不引入新依赖，复用 ``requests`` + 现有 FMP API key。
失败时返回空列表 + status，不抛异常。
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests

from ...config import Config

logger = logging.getLogger("finrex.financial.news_provider")

FMP_NEWS_URL = "https://financialmodelingprep.com/api/v3/stock_news"
FMP_CRYPTO_NEWS_URL = "https://financialmodelingprep.com/api/v3/crypto_news"
FMP_PRESS_RELEASES_URL = "https://financialmodelingprep.com/api/v3/press-releases/{symbol}"
FMP_GENERAL_NEWS_URL = "https://financialmodelingprep.com/api/v4/general_news"


def _fmp_api_key() -> Optional[str]:
    return getattr(Config, "FMP_API_KEY", None) or os.environ.get("FMP_API_KEY")


def _normalize_news_item(raw: Dict[str, Any]) -> Dict[str, Any]:
    title = (raw.get("title") or "").strip()
    text = (raw.get("text") or raw.get("snippet") or raw.get("content") or "").strip()
    text_empty = not text
    if text_empty and title:
        text = title  # fallback so downstream sentiment has something to score
    return {
        "title": title,
        "text": text,
        "url": raw.get("url") or raw.get("link") or "",
        "site": raw.get("site") or raw.get("source") or "",
        "published_at": raw.get("publishedDate") or raw.get("date") or "",
        "tickers": raw.get("symbol") or raw.get("tickers") or "",
        "text_empty": text_empty,
        # Items with no body downweighted in sentiment aggregation
        "weight": 0.3 if text_empty else 1.0,
    }


def _format_fmp_date(value: Optional[datetime]) -> Optional[str]:
    if not value:
        return None
    return value.strftime("%Y-%m-%d")


def _parse_published(value: Any) -> Optional[datetime]:
    if not value:
        return None
    s = str(value).strip().replace("Z", "+00:00")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=None) if dt.tzinfo else dt
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(s)
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    except ValueError:
        return None


def _filter_by_hours(items: List[Dict[str, Any]], hours: int) -> List[Dict[str, Any]]:
    if not hours or hours <= 0:
        return items
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    out: List[Dict[str, Any]] = []
    for it in items:
        dt = _parse_published(it.get("published_at"))
        if dt is None or dt >= cutoff:
            out.append(it)
    return out


def _ticker_tokens(value: Any) -> List[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        raw = " ".join(str(v) for v in value)
    else:
        raw = str(value)
    return [token.upper() for token in re.findall(r"[A-Za-z0-9]+(?:[-.][A-Za-z0-9]+)?", raw)]


def _base_symbol(symbol: str) -> str:
    raw = (symbol or "").strip().upper()
    if "-" in raw:
        raw = raw.split("-", 1)[0]
    if "." in raw:
        raw = raw.split(".", 1)[0]
    return raw


def _matches_target_ticker(item: Dict[str, Any], symbol: str) -> bool:
    target = _base_symbol(symbol)
    tokens = _ticker_tokens(item.get("tickers"))
    if not target or not tokens:
        return True
    return any(_base_symbol(token) == target for token in tokens)


def _clean_selected_seed_text(text: str) -> str:
    """Strip internal seed metadata and placeholder observed-comment blocks."""
    if not text:
        return ""
    section = "body"
    kept: List[str] = []
    for raw_line in str(text).splitlines():
        line = raw_line.strip()
        marker = re.match(r"^=+\s*(.*?)\s*=+$", line)
        if marker:
            section = marker.group(1).strip().lower()
            continue
        if section in {"source metadata", "observed comment layer"}:
            continue
        if not line:
            if kept and kept[-1] != "":
                kept.append("")
            continue
        kept.append(line)
    return "\n".join(kept).strip()


class NewsProvider:
    """新闻 + 评论 Provider。"""

    @staticmethod
    def fetch_news(
        symbol: str,
        asset_type: str = "stock",
        limit: int = 20,
        hours: Optional[int] = None,
    ) -> Dict[str, Any]:
        """拉取与 symbol 相关的新闻。

        Args:
            hours: 仅返回最近 N 小时内发布的新闻（FMP v3 不支持原生 from/to
                参数稳定过滤，故在客户端做时间裁剪）；None 表示不限时间。

        Returns:
            {
                "ok": bool,
                "items": [normalized_news...],
                "source": "fmp" | "fmp_crypto" | "none",
                "error": str | None,
            }
        """
        result: Dict[str, Any] = {"ok": False, "items": [], "source": "none", "error": None}
        api_key = _fmp_api_key()
        if not api_key:
            result["error"] = "FMP_API_KEY not configured"
            return result
        if not symbol or asset_type == "event":
            result["error"] = "no symbol"
            return result

        url = FMP_CRYPTO_NEWS_URL if asset_type == "crypto" else FMP_NEWS_URL
        # request more than limit so post-hoc time filter still yields enough rows
        fetch_n = min(max(limit * 3, 30), 100) if hours else min(max(limit, 1), 50)
        params: Dict[str, Any] = {"limit": fetch_n, "apikey": api_key}
        if asset_type != "crypto":
            params["tickers"] = symbol.upper().split("-")[0]

        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            raw_items = resp.json() or []
        except Exception as exc:  # noqa: BLE001
            logger.warning("FMP news fetch failed for %s: %s", symbol, exc)
            result["error"] = str(exc)
            return result

        items = [_normalize_news_item(it) for it in raw_items if isinstance(it, dict)]
        if hours:
            items = _filter_by_hours(items, hours)
        items = items[:limit]
        result.update(ok=bool(items), items=items, source="fmp_crypto" if asset_type == "crypto" else "fmp")
        return result

    @staticmethod
    def fetch_press_releases(symbol: str, limit: int = 10, hours: Optional[int] = 168) -> Dict[str, Any]:
        """拉取公司财报新闻稿。默认窗口 168h（7 天）。"""
        result: Dict[str, Any] = {"ok": False, "items": [], "source": "fmp_press", "error": None}
        api_key = _fmp_api_key()
        if not api_key or not symbol:
            result["error"] = "FMP_API_KEY not configured" if not api_key else "no symbol"
            return result
        url = FMP_PRESS_RELEASES_URL.format(symbol=symbol.upper().split("-")[0])
        try:
            resp = requests.get(url, params={"limit": min(max(limit * 2, 20), 50), "apikey": api_key}, timeout=10)
            resp.raise_for_status()
            raw_items = resp.json() or []
        except Exception as exc:  # noqa: BLE001
            logger.warning("FMP press-releases fetch failed for %s: %s", symbol, exc)
            result["error"] = str(exc)
            return result
        items: List[Dict[str, Any]] = []
        for it in raw_items:
            if not isinstance(it, dict):
                continue
            items.append(_normalize_news_item({
                "title": it.get("title"),
                "text": it.get("text") or it.get("content"),
                "url": it.get("url") or "",
                "site": "press_release",
                "publishedDate": it.get("date") or it.get("publishedDate"),
                "symbol": it.get("symbol") or symbol,
            }))
        if hours:
            items = _filter_by_hours(items, hours)
        items = items[:limit]
        result.update(ok=bool(items), items=items)
        return result

    @staticmethod
    def fetch_general_news(query: str, limit: int = 10, hours: Optional[int] = 72) -> Dict[str, Any]:
        """拉取大盘 / 行业级新闻（按关键词），用于补全个股新闻不足。"""
        result: Dict[str, Any] = {"ok": False, "items": [], "source": "fmp_general", "error": None}
        api_key = _fmp_api_key()
        if not api_key:
            result["error"] = "FMP_API_KEY not configured"
            return result
        try:
            resp = requests.get(
                FMP_GENERAL_NEWS_URL,
                params={"page": 0, "size": min(max(limit * 2, 20), 50), "apikey": api_key},
                timeout=10,
            )
            resp.raise_for_status()
            raw_items = resp.json() or []
        except Exception as exc:  # noqa: BLE001
            logger.warning("FMP general news fetch failed: %s", exc)
            result["error"] = str(exc)
            return result
        q = (query or "").strip().lower()
        items: List[Dict[str, Any]] = []
        for it in raw_items:
            if not isinstance(it, dict):
                continue
            normalized = _normalize_news_item(it)
            if q:
                hay = f"{normalized['title']} {normalized['text']}".lower()
                if q not in hay:
                    continue
            items.append(normalized)
        if hours:
            items = _filter_by_hours(items, hours)
        items = items[:limit]
        result.update(ok=bool(items), items=items)
        return result

    @staticmethod
    def normalize_user_comments(comments: List[Any]) -> List[Dict[str, Any]]:
        """将用户在 Step1 输入的评论统一成 news_item 形态。"""
        normalized: List[Dict[str, Any]] = []
        if not isinstance(comments, list):
            return normalized
        for idx, item in enumerate(comments):
            if isinstance(item, str):
                text = item.strip()
                if not text:
                    continue
                normalized.append({
                    "title": f"User comment #{idx + 1}",
                    "text": text,
                    "url": "",
                    "site": "user_input",
                    "published_at": datetime.now().isoformat(),
                    "tickers": "",
                })
            elif isinstance(item, dict):
                text = (item.get("text") or item.get("content") or "").strip()
                if not text:
                    continue
                normalized.append({
                    "title": item.get("title") or f"User comment #{idx + 1}",
                    "text": text,
                    "url": item.get("url") or "",
                    "site": item.get("site") or "user_input",
                    "published_at": item.get("date") or datetime.now().isoformat(),
                    "tickers": item.get("tickers") or "",
                })
        return normalized

    @staticmethod
    def normalize_selected_articles(articles: List[Any]) -> List[Dict[str, Any]]:
        """将 Step1 选中的 FMP/Binance/manual seed 统一成 news_item 形态。"""
        normalized: List[Dict[str, Any]] = []
        if not isinstance(articles, list):
            return normalized
        for idx, item in enumerate(articles):
            if isinstance(item, str):
                text = item.strip()
                if not text:
                    continue
                normalized.append({
                    "title": f"Selected article #{idx + 1}",
                    "text": text,
                    "url": "",
                    "site": "selected_seed",
                    "published_at": datetime.now().isoformat(),
                    "tickers": "",
                    "source": "selected_seed",
                })
                continue
            if not isinstance(item, dict):
                continue
            text = _clean_selected_seed_text(item.get("text") or item.get("content") or item.get("body") or item.get("summary") or "")
            title = (item.get("title") or f"Selected article #{idx + 1}").strip()
            if not text and not title:
                continue
            normalized.append({
                "title": title,
                "text": text or title,
                "url": item.get("url") or item.get("link") or "",
                "site": item.get("site") or item.get("source") or item.get("source_type") or "selected_seed",
                "published_at": item.get("published_at") or item.get("publishedDate") or item.get("date") or item.get("created_at") or "",
                "tickers": item.get("tickers") or "",
                "source": item.get("source") or item.get("source_type") or "selected_seed",
            })
        return normalized

    @classmethod
    def collect_corpus(
        cls,
        symbol: str,
        asset_type: str,
        user_comments: Optional[List[Any]] = None,
        selected_articles: Optional[List[Any]] = None,
        news_limit: int = 20,
        hours: Optional[int] = None,
        include_press_releases: bool = False,
        include_general_news: bool = False,
        general_news_query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """聚合新闻 + 用户评论，作为情绪打分输入。

        Returns:
            {
                "news": [...],
                "comments": [...],
                "all": [...],   # news + comments，用于统一打分
                "news_status": {...},
            }
        """
        news_status = cls.fetch_news(symbol, asset_type=asset_type, limit=news_limit, hours=hours)
        news_items = list(news_status["items"])

        press_status: Dict[str, Any] = {"ok": False, "items": [], "source": "fmp_press"}
        general_status: Dict[str, Any] = {"ok": False, "items": [], "source": "fmp_general"}
        if include_press_releases and symbol and asset_type == "stock":
            press_status = cls.fetch_press_releases(symbol, limit=10, hours=hours or 168)
            news_items.extend(press_status.get("items") or [])
        if include_general_news and asset_type == "stock":
            general_status = cls.fetch_general_news(
                query=general_news_query or symbol,
                limit=8,
                hours=hours or 72,
            )
            news_items.extend(general_status.get("items") or [])

        articles = [
            item for item in cls.normalize_selected_articles(selected_articles or [])
            if _matches_target_ticker(item, symbol)
        ]
        comments = cls.normalize_user_comments(user_comments or [])
        return {
            "news": news_items,
            "articles": articles,
            "comments": comments,
            "all": news_items + articles + comments,
            "news_status": {k: v for k, v in news_status.items() if k != "items"},
            "press_status": {k: v for k, v in press_status.items() if k != "items"},
            "general_status": {k: v for k, v in general_status.items() if k != "items"},
        }
