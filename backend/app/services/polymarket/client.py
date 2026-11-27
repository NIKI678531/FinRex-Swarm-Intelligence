"""Polymarket REST client (read-only).

Wraps the public Gamma metadata API and CLOB market-data API. Mirrors the
disk-cache + stale-fallback pattern used by
``app.services.asset_forecast.market_data`` so we degrade gracefully on
network hiccups without spamming the upstream.

Design rules:
  * **No signing, no wallets, no orders.** This client is strictly read-only.
  * Order book endpoints are NEVER cached — execution decisions need
    real-time depth.
  * Market metadata and price history are cached on disk with a short TTL.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests

from ...config import Config
from .orderbook import OrderBook

logger = logging.getLogger("finrex.polymarket.client")

DEFAULT_GAMMA_BASE = "https://gamma-api.polymarket.com"
DEFAULT_CLOB_BASE = "https://clob.polymarket.com"
DEFAULT_CACHE_TTL_SECONDS = 600  # 10 minutes
DEFAULT_TIMEOUT_SECONDS = 10
USER_AGENT = "FinRex-ValidationLab/1.0 (+research only; no trading)"


class PolymarketAPIError(RuntimeError):
    """Raised when the upstream Polymarket API returns an unrecoverable error."""


class PolymarketClient:
    def __init__(
        self,
        gamma_base: Optional[str] = None,
        clob_base: Optional[str] = None,
        cache_dir: Optional[str] = None,
        cache_ttl_seconds: Optional[int] = None,
        timeout: Optional[int] = None,
        session: Optional[requests.Session] = None,
    ):
        self.gamma_base = (
            gamma_base
            or getattr(Config, "POLYMARKET_GAMMA_BASE", None)
            or DEFAULT_GAMMA_BASE
        ).rstrip("/")
        self.clob_base = (
            clob_base
            or getattr(Config, "POLYMARKET_CLOB_BASE", None)
            or DEFAULT_CLOB_BASE
        ).rstrip("/")
        self.cache_ttl = int(
            cache_ttl_seconds
            or getattr(Config, "POLYMARKET_CACHE_TTL", None)
            or DEFAULT_CACHE_TTL_SECONDS
        )
        self.timeout = int(timeout or DEFAULT_TIMEOUT_SECONDS)
        self.cache_dir = cache_dir or os.path.join(
            getattr(Config, "UPLOAD_FOLDER", "uploads"), "polymarket_cache"
        )
        os.makedirs(self.cache_dir, exist_ok=True)
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})

    # ==================================================================
    # Public API — Gamma (markets metadata)
    # ==================================================================
    def list_active_markets(
        self,
        tag: Optional[str] = None,
        limit: int = 500,
        closed: bool = False,
    ) -> List[Dict[str, Any]]:
        """List currently active markets. Optional `tag` filter, e.g. 'Crypto'."""
        params: Dict[str, Any] = {
            "active": "true",
            "closed": "false" if not closed else "true",
            "limit": int(limit),
        }
        if tag:
            params["tag"] = tag
        cache_key = f"gamma_markets_{tag or 'all'}_{limit}_{int(closed)}"
        return self._cached_get(
            url=f"{self.gamma_base}/markets",
            params=params,
            cache_key=cache_key,
            ttl=self.cache_ttl,
            list_response=True,
        )

    def get_market(self, market_id: str) -> Dict[str, Any]:
        """Fetch a single market by id (Gamma)."""
        cache_key = f"gamma_market_{market_id}"
        data = self._cached_get(
            url=f"{self.gamma_base}/markets/{market_id}",
            params=None,
            cache_key=cache_key,
            ttl=self.cache_ttl,
        )
        return data or {}

    def search_markets_by_slug_prefix(
        self,
        slug_prefix: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Search markets whose slug starts with `slug_prefix`.

        Used by the daily BTC matcher (e.g. 'bitcoin-up-or-down-on-').
        Falls back to a client-side filter on `list_active_markets`.
        """
        markets = self.list_active_markets(limit=limit)
        prefix = slug_prefix.lower()
        return [m for m in markets if str(m.get("slug", "")).lower().startswith(prefix)]

    def find_resolved_market_at(
        self,
        anchor_utc: datetime,
        slug_pattern: str,
    ) -> Optional[Dict[str, Any]]:
        """For historical replay: find a closed market whose slug matches
        ``slug_pattern`` and whose endDate is within ±2h of ``anchor_utc``.
        """
        # Search closed markets via gamma, filter client-side.
        params = {
            "closed": "true",
            "limit": 500,
            "ascending": "false",
        }
        cache_key = f"gamma_closed_{slug_pattern}_{anchor_utc.strftime('%Y%m%d')}"
        candidates = self._cached_get(
            url=f"{self.gamma_base}/markets",
            params=params,
            cache_key=cache_key,
            ttl=86400,  # closed markets don't change
            list_response=True,
        ) or []
        target = anchor_utc.astimezone(timezone.utc)
        best: Optional[Dict[str, Any]] = None
        best_delta = timedelta(hours=2, seconds=1)
        pat = slug_pattern.lower()
        for m in candidates:
            slug = str(m.get("slug", "")).lower()
            if pat not in slug:
                continue
            end_iso = m.get("endDate") or m.get("end_date_iso")
            if not end_iso:
                continue
            try:
                end_dt = datetime.fromisoformat(str(end_iso).replace("Z", "+00:00"))
            except ValueError:
                continue
            delta = abs(end_dt - target)
            if delta <= best_delta:
                best_delta = delta
                best = m
        return best

    # ==================================================================
    # Public API — CLOB (live market data)
    # ==================================================================
    def get_midpoint(self, token_id: str) -> Optional[float]:
        """Midpoint price (cached briefly — stale tolerated for UI)."""
        cache_key = f"clob_mid_{token_id}"
        data = self._cached_get(
            url=f"{self.clob_base}/midpoint",
            params={"token_id": token_id},
            cache_key=cache_key,
            ttl=60,
        )
        if not data:
            return None
        try:
            return float(data.get("mid"))
        except (TypeError, ValueError):
            return None

    def get_price_history(
        self,
        token_id: str,
        interval: str = "1d",
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Historical prices for a CLOB outcome token."""
        params: Dict[str, Any] = {"market": token_id, "interval": interval}
        if start_ts is not None:
            params["startTs"] = int(start_ts)
        if end_ts is not None:
            params["endTs"] = int(end_ts)
        cache_key = f"clob_hist_{token_id}_{interval}_{start_ts}_{end_ts}"
        data = self._cached_get(
            url=f"{self.clob_base}/prices-history",
            params=params,
            cache_key=cache_key,
            ttl=self.cache_ttl,
        )
        if not data:
            return []
        if isinstance(data, dict):
            return data.get("history") or data.get("data") or []
        return data if isinstance(data, list) else []

    def get_book(self, token_id: str) -> OrderBook:
        """Live order book — NEVER cached.

        Execution decisions and the market-impact display both depend on the
        freshest possible depth. A stale book would silently inflate paper
        PnL.
        """
        url = f"{self.clob_base}/book"
        try:
            resp = self.session.get(url, params={"token_id": token_id}, timeout=self.timeout)
            resp.raise_for_status()
            payload = resp.json() or {}
        except (requests.RequestException, ValueError) as exc:
            logger.error("polymarket get_book failed for %s: %s", token_id, exc)
            raise PolymarketAPIError(f"get_book failed: {exc}") from exc
        return OrderBook.from_clob(token_id, payload)

    def get_books(self, token_ids: List[str]) -> Dict[str, OrderBook]:
        """Batch wrapper. Sequential — keep call count small."""
        out: Dict[str, OrderBook] = {}
        for tid in token_ids:
            try:
                out[tid] = self.get_book(tid)
            except PolymarketAPIError as exc:
                logger.warning("skipping book for %s: %s", tid, exc)
        return out

    # ==================================================================
    # Internal — cache-aware GET
    # ==================================================================
    def _cached_get(
        self,
        url: str,
        params: Optional[Dict[str, Any]],
        cache_key: str,
        ttl: int,
        list_response: bool = False,
    ) -> Any:
        cached, cached_age = self._read_cache(cache_key)
        if cached is not None and cached_age is not None and cached_age <= ttl:
            return cached
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            payload = resp.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning(
                "polymarket GET %s failed (%s); using stale cache age=%s",
                url, exc, cached_age,
            )
            return cached if cached is not None else ([] if list_response else None)
        # Some Gamma endpoints return {"data": [...]} ; normalize.
        if list_response and isinstance(payload, dict):
            payload = payload.get("data") or payload.get("markets") or []
        self._write_cache(cache_key, payload)
        return payload

    def _cache_path(self, cache_key: str) -> str:
        safe = "".join(c if c.isalnum() or c in ("_", "-", ".") else "_" for c in cache_key)
        return os.path.join(self.cache_dir, f"{safe}.json")

    def _read_cache(self, cache_key: str):
        path = self._cache_path(cache_key)
        if not os.path.exists(path):
            return None, None
        try:
            with open(path, "r", encoding="utf-8") as f:
                wrapped = json.load(f)
        except (OSError, ValueError) as exc:
            logger.warning("polymarket cache read failed: %s", exc)
            return None, None
        ts = wrapped.get("_fetched_at")
        try:
            age = time.time() - float(ts)
        except (TypeError, ValueError):
            return wrapped.get("data"), None
        return wrapped.get("data"), age

    def _write_cache(self, cache_key: str, data: Any) -> None:
        path = self._cache_path(cache_key)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"_fetched_at": time.time(), "data": data}, f, ensure_ascii=False)
        except OSError as exc:
            logger.warning("polymarket cache write failed: %s", exc)


# ----------------------------------------------------------------------
# CLI helper: ``python -m app.services.polymarket.client search bitcoin``
# ----------------------------------------------------------------------
def _cli() -> None:
    import sys

    args = sys.argv[1:]
    if not args:
        print("usage: client.py [search <keyword> | book <token_id> | mid <token_id>]")
        return
    client = PolymarketClient()
    cmd = args[0]
    if cmd == "search":
        kw = (args[1] if len(args) > 1 else "bitcoin").lower()
        markets = client.list_active_markets(limit=200)
        hits = [m for m in markets if kw in str(m.get("slug", "")).lower() or kw in str(m.get("question", "")).lower()]
        for m in hits[:20]:
            print(f"{m.get('id')} | {m.get('endDate')} | {m.get('slug')}")
    elif cmd == "book" and len(args) > 1:
        ob = client.get_book(args[1])
        print(f"best_ask={ob.best_ask} best_bid={ob.best_bid} mid={ob.midpoint}")
        print(f"ask_notional=${ob.total_ask_notional():.0f} bid_notional=${ob.total_bid_notional():.0f}")
    elif cmd == "mid" and len(args) > 1:
        print(client.get_midpoint(args[1]))
    else:
        print("unknown command")


if __name__ == "__main__":
    _cli()
