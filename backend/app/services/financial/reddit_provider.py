"""Reddit 帖子 Provider（公开 JSON 端点，零配置）。

为美股预测拉取 wallstreetbets / stocks / investing / NVDA / options 等
subreddit 的最新帖子。传入 symbol 时按关键词过滤；不传 symbol 时抓取
默认金融社区的最新讨论。

- 优先使用公开 JSON：``https://www.reddit.com/r/{sub}/search.json?q={q}&sort=new``
- 不依赖 PRAW；如未来需要更高频率可扩展走 PRAW 凭证。
- 60s 磁盘缓存，缓解 429。
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from ...config import Config

logger = logging.getLogger("finrex.financial.reddit_provider")

DEFAULT_SUBREDDITS = ["wallstreetbets", "stocks", "investing", "options"]
TICKER_SPECIFIC_SUBS = {
    "NVDA": ["NVDA_Stock", "wallstreetbets"],
    "TSLA": ["teslainvestorsclub", "wallstreetbets"],
    "AAPL": ["AAPL", "wallstreetbets"],
    "AMD": ["AMD_Stock", "wallstreetbets"],
}

_USER_AGENT = "FinRex/0.1 (sentiment-research)"
_CACHE_TTL_SECONDS = 60


def _cache_root() -> str:
    base = getattr(Config, "UPLOAD_ROOT", None) or os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "uploads"
    )
    root = os.path.abspath(os.path.join(base, "reddit_cache"))
    os.makedirs(root, exist_ok=True)
    return root


def _cache_path(key: str) -> str:
    safe = key.replace("/", "_").replace(":", "_")
    return os.path.join(_cache_root(), f"{safe}.json")


def _read_cache(key: str) -> Optional[List[Dict[str, Any]]]:
    path = _cache_path(key)
    if not os.path.exists(path):
        return None
    if (time.time() - os.path.getmtime(path)) > _CACHE_TTL_SECONDS:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def _write_cache(key: str, items: List[Dict[str, Any]]) -> None:
    try:
        with open(_cache_path(key), "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001
        logger.debug("reddit cache write failed: %s", exc)


def _normalize_post(raw: Dict[str, Any], subreddit: str) -> Dict[str, Any]:
    data = raw.get("data") if isinstance(raw, dict) else None
    if not isinstance(data, dict):
        return {}
    title = (data.get("title") or "").strip()
    selftext = (data.get("selftext") or "").strip()
    text = selftext or title
    created = data.get("created_utc")
    published = ""
    if isinstance(created, (int, float)) and created > 0:
        try:
            published = datetime.utcfromtimestamp(float(created)).isoformat()
        except (OverflowError, OSError):
            published = ""
    permalink = data.get("permalink") or ""
    url = f"https://www.reddit.com{permalink}" if permalink else (data.get("url") or "")
    score = float(data.get("score") or 0)
    num_comments = float(data.get("num_comments") or 0)
    return {
        "title": title,
        "text": text,
        "url": url,
        "site": f"reddit/{subreddit}",
        "published_at": published,
        "tickers": "",
        "like_count": score,
        "reply_count": num_comments,
        "post_id": data.get("id") or "",
        "subreddit": subreddit,
        "author": data.get("author") or "",
        "text_empty": not selftext,
        "weight": 1.0 if selftext else 0.6,
        "source": "reddit",
        "source_type": "reddit",
    }


class RedditProvider:
    """Reddit 公开 JSON 拉取（symbol 可选）。"""

    @staticmethod
    def fetch_posts(
        symbol: str,
        subreddits: Optional[List[str]] = None,
        limit_per_sub: int = 8,
        timeout: int = 8,
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {"ok": False, "items": [], "source": "reddit_public", "error": None}
        sym = (symbol or "").strip().upper()
        subs = subreddits or ((TICKER_SPECIFIC_SUBS.get(sym, []) if sym else []) + DEFAULT_SUBREDDITS)
        subs = list(dict.fromkeys([s for s in subs if s]))[:6]

        all_items: List[Dict[str, Any]] = []
        errors: List[str] = []
        for sub in subs:
            cache_key = f"{sub}__{sym or 'latest'}__{limit_per_sub}"
            cached = _read_cache(cache_key)
            if cached is not None:
                all_items.extend(cached)
                continue
            params = {"limit": max(5, min(limit_per_sub, 25))}
            if sym:
                url = f"https://www.reddit.com/r/{sub}/search.json"
                params.update({
                    "q": sym,
                    "restrict_sr": 1,
                    "sort": "new",
                    "t": "week",
                })
            else:
                url = f"https://www.reddit.com/r/{sub}/new.json"
            try:
                resp = requests.get(
                    url,
                    params=params,
                    headers={"User-Agent": _USER_AGENT},
                    timeout=timeout,
                )
                resp.raise_for_status()
                payload = resp.json()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{sub}: {exc}")
                logger.warning("Reddit fetch failed (r/%s, %s): %s", sub, sym, exc)
                continue
            children = ((payload or {}).get("data") or {}).get("children") or []
            sub_items: List[Dict[str, Any]] = []
            for c in children:
                normalized = _normalize_post(c, sub)
                if normalized and (normalized["title"] or normalized["text"]):
                    sub_items.append(normalized)
            _write_cache(cache_key, sub_items)
            all_items.extend(sub_items)

        # Dedup by post_id
        seen: set = set()
        unique: List[Dict[str, Any]] = []
        for it in all_items:
            pid = it.get("post_id") or it.get("url")
            if pid in seen:
                continue
            seen.add(pid)
            unique.append(it)
        # Newest first
        unique.sort(key=lambda x: x.get("published_at") or "", reverse=True)
        result.update(ok=bool(unique), items=unique, error="; ".join(errors) if errors and not unique else None)
        return result
