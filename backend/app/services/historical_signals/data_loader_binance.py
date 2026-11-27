"""Binance Square (Cloudflare D1) historical loader for backtest.

Reuses the credentials configured in `Config.CLOUDFLARE_D1_*`.
Cached as JSONL under `<UPLOAD_FOLDER>/backtest/sentiment/binance/<yyyy-mm>.jsonl`.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from ...config import Config

logger = logging.getLogger("finrex.backtest.binance")

_PAGE_SIZE = 200
_MAX_PAGES = 40


def _cache_dir() -> str:
    base = os.path.join(Config.UPLOAD_FOLDER, "backtest", "sentiment", "binance")
    os.makedirs(base, exist_ok=True)
    return base


def _cache_path(year_month: str) -> str:
    return os.path.join(_cache_dir(), f"{year_month}.jsonl")


def _d1_query(sql: str, params: list, timeout: int = 20) -> list:
    account_id = Config.CLOUDFLARE_D1_ACCOUNT_ID
    db_id = Config.CLOUDFLARE_D1_DATABASE_ID
    token = Config.CLOUDFLARE_D1_API_TOKEN
    if not (account_id and db_id and token):
        raise RuntimeError("Cloudflare D1 credentials missing")
    url = (
        f"https://api.cloudflare.com/client/v4/accounts/{account_id}"
        f"/d1/database/{db_id}/query"
    )
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"sql": sql, "params": params},
        timeout=timeout,
    )
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("success"):
        raise RuntimeError(f"D1 query failed: {payload.get('errors')}")
    blocks = payload.get("result") or []
    return blocks[0].get("results") if blocks else []


def _normalize(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    publish_time = row.get("publish_time")
    if not publish_time:
        return None
    try:
        ts = datetime.fromtimestamp(int(publish_time), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None
    return {
        "source": "binance_d1",
        "title": row.get("title") or "",
        "text": row.get("content") or row.get("sub_title") or "",
        "symbol": row.get("trading_pairs_json") or "",
        "site": "Binance Square",
        "author": row.get("author_name") or "",
        "url": row.get("web_link") or row.get("share_link") or "",
        "published_at": ts.isoformat(),
        "comment_count": row.get("comment_count") or 0,
        "like_count": row.get("like_count") or 0,
    }


def fetch_window(
    start: datetime,
    end: datetime,
    *,
    keyword: Optional[str] = None,
    use_cache: bool = True,
) -> List[Dict[str, Any]]:
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    if use_cache:
        cached: List[Dict[str, Any]] = []
        cur_year, cur_month = start.year, start.month
        while (cur_year, cur_month) <= (end.year, end.month):
            ym = f"{cur_year:04d}-{cur_month:02d}"
            path = _cache_path(ym)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            cached.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            cur_month += 1
            if cur_month > 12:
                cur_month = 1
                cur_year += 1
        if cached:
            return [c for c in cached if start.isoformat() <= c.get("published_at", "") <= end.isoformat()]

    where = ["publish_time >= ?", "publish_time <= ?"]
    params: list = [int(start.timestamp()), int(end.timestamp())]
    if keyword:
        where.append("(title LIKE ? OR content LIKE ?)")
        like = f"%{keyword}%"
        params.extend([like, like])

    where_sql = " WHERE " + " AND ".join(where)
    base_sql = (
        "SELECT id, source, title, sub_title, content, author_name, "
        "publish_time, web_link, share_link, like_count, comment_count, "
        "view_count, trading_pairs_json "
        f"FROM posts{where_sql} ORDER BY publish_time DESC LIMIT ? OFFSET ?"
    )

    collected: List[Dict[str, Any]] = []
    for page in range(_MAX_PAGES):
        try:
            rows = _d1_query(base_sql, params + [_PAGE_SIZE, page * _PAGE_SIZE])
        except Exception as exc:
            logger.warning("D1 fetch failed page=%d err=%s", page, exc)
            break
        if not rows:
            break
        for row in rows:
            n = _normalize(row)
            if n is not None:
                collected.append(n)
        if len(rows) < _PAGE_SIZE:
            break

    by_month: Dict[str, List[Dict[str, Any]]] = {}
    for item in collected:
        ts = datetime.fromisoformat(item["published_at"])
        ym = ts.strftime("%Y-%m")
        by_month.setdefault(ym, []).append(item)
    for ym, items in by_month.items():
        with open(_cache_path(ym), "w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

    return collected
