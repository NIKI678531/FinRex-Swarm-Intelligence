"""Read-only matcher for Polymarket weekly BTC price-range markets."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .client import PolymarketClient

logger = logging.getLogger("finrex.polymarket.weekly")

WEEKLY_SLUG_PREFIX = "what-price-will-bitcoin-hit-"
BTC_KEYWORDS = ("bitcoin", "btc")


class WeeklyBTCMarketMatcher:
    def __init__(self, client: Optional[PolymarketClient] = None):
        self.client = client or PolymarketClient()

    def weekly_payload(self, *, mode: str = "current", limit: int = 10) -> Dict[str, Any]:
        safe_limit = min(max(int(limit or 10), 1), 20)
        source_status = {"available": True, "source": "polymarket_gamma_clob", "errors": []}
        try:
            active = self._markets(closed=False, limit=250)
        except Exception as exc:  # noqa: BLE001
            active = []
            source_status["errors"].append(f"active: {exc}")
        try:
            closed = self._markets(closed=True, limit=500) if mode == "history" else []
        except Exception as exc:  # noqa: BLE001
            closed = []
            source_status["errors"].append(f"closed: {exc}")

        active_weeklies = self._filter_weekly(active)
        closed_weeklies = self._filter_weekly(closed)
        current = self._serialize(active_weeklies[0], include_midpoints=True) if active_weeklies else None
        history = [self._serialize(m, include_midpoints=False) for m in closed_weeklies[:safe_limit]]

        if source_status["errors"] and not current and not history:
            source_status["available"] = False
        source_status.update({
            "active_candidates": len(active_weeklies),
            "history_candidates": len(closed_weeklies),
        })
        return {"current": current, "history": history, "source_status": source_status}

    def _markets(self, *, closed: bool, limit: int) -> List[Dict[str, Any]]:
        # Reuse the client's cache-aware request layer but avoid list_active_markets
        # because closed historical markets are often not active=true.
        params = {
            "closed": "true" if closed else "false",
            "active": "false" if closed else "true",
            "limit": int(limit),
            "ascending": "false",
        }
        data = self.client._cached_get(  # intentional: client has no general search method yet
            url=f"{self.client.gamma_base}/markets",
            params=params,
            cache_key=f"weekly_btc_markets_{int(closed)}_{limit}",
            ttl=600 if not closed else 86400,
            list_response=True,
        )
        return data if isinstance(data, list) else []

    def _filter_weekly(self, markets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out = []
        for market in markets:
            slug = str(market.get("slug") or "").lower()
            question = str(market.get("question") or "").lower()
            if WEEKLY_SLUG_PREFIX in slug or ("what price will" in question and any(k in question for k in BTC_KEYWORDS)):
                out.append(market)
        out.sort(key=lambda m: str(m.get("endDate") or m.get("end_date_iso") or ""), reverse=True)
        return out

    def _serialize(self, market: Dict[str, Any], *, include_midpoints: bool) -> Dict[str, Any]:
        outcomes = self._extract_outcomes(market)
        if include_midpoints:
            for outcome in outcomes:
                token_id = outcome.get("token_id")
                if token_id:
                    try:
                        mid = self.client.get_midpoint(token_id)
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("midpoint failed token=%s err=%s", token_id, exc)
                        mid = None
                    if mid is not None:
                        outcome["yes_price"] = mid
                        outcome["no_price"] = max(0.0, min(1.0, 1.0 - mid))
        end_iso = market.get("endDate") or market.get("end_date_iso")
        return {
            "id": str(market.get("id") or market.get("conditionId") or ""),
            "slug": str(market.get("slug") or ""),
            "question": str(market.get("question") or ""),
            "end_date_utc": _iso(end_iso),
            "volume_usd": _float_any(market, ("volume", "volumeNum", "volume_usd")),
            "liquidity_usd": _float_any(market, ("liquidity", "liquidityNum", "liquidity_usd")),
            "outcomes": outcomes,
            "raw_url": f"https://polymarket.com/event/{market.get('slug')}" if market.get("slug") else "",
        }

    def _extract_outcomes(self, market: Dict[str, Any]) -> List[Dict[str, Any]]:
        names = _jsonish_list(market.get("outcomes")) or _jsonish_list(market.get("shortOutcomes"))
        prices = _jsonish_list(market.get("outcomePrices"))
        tokens = _jsonish_list(market.get("clobTokenIds")) or _jsonish_list(market.get("tokens"))
        if tokens and all(isinstance(t, dict) for t in tokens):
            names = names or [t.get("outcome") or t.get("name") for t in tokens]
            token_ids = [t.get("token_id") or t.get("tokenId") or t.get("id") for t in tokens]
        else:
            token_ids = [str(t) for t in tokens] if tokens else []
        out: List[Dict[str, Any]] = []
        for idx, name in enumerate(names or []):
            label = str(name or f"Outcome {idx + 1}")
            yes = _float(prices[idx] if idx < len(prices or []) else None)
            low, high = _parse_range(label)
            out.append({
                "index": idx,
                "label": label,
                "low": low,
                "high": high,
                "token_id": str(token_ids[idx]) if idx < len(token_ids) else "",
                "yes_price": yes,
                "no_price": max(0.0, min(1.0, 1.0 - yes)) if yes is not None else None,
                "volume_usd": 0.0,
                "liquidity_usd": 0.0,
            })
        return out


def _jsonish_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return [part.strip() for part in value.split(",") if part.strip()]
    return []


def _parse_range(label: str) -> Tuple[Optional[float], Optional[float]]:
    clean = label.replace(",", "")
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", clean)]
    if not nums:
        return None, None
    if clean.strip().startswith("<"):
        return None, nums[0]
    if clean.strip().startswith(">") or clean.strip().lower().startswith("above"):
        return nums[0], None
    if len(nums) >= 2:
        return nums[0], nums[1]
    return nums[0], nums[0]


def _float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _float_any(row: Dict[str, Any], keys: Tuple[str, ...]) -> float:
    for key in keys:
        value = _float(row.get(key))
        if value is not None:
            return value
    return 0.0


def _iso(value: Any) -> str:
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return str(value)

