"""Match a Polymarket daily BTC up/down market to a FinRex forecast cycle.

Polymarket runs daily binary markets like "Bitcoin Up or Down on May 12?"
that resolve at 12:00 UTC each day. The slug pattern is consistent enough
to be matched directly. We additionally validate:

  * `endDate` must be within ±2h of the cycle anchor.
  * Market must be `active=true && closed=false`.
  * Liquidity (sum of book notional or `liquidity` field on Gamma) must
    exceed the configured minimum, otherwise execution would slip badly.

Anything that does not pass returns `None` and the execution engine simply
skips this cycle — we never trade into a thin or wrong-day market.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .client import PolymarketClient

logger = logging.getLogger("finrex.polymarket.matcher")

# Slug template (live markets).
DAILY_BTC_SLUG_PREFIX = "bitcoin-up-or-down-on-"
END_DATE_TOLERANCE_HOURS = 2
DEFAULT_MIN_LIQUIDITY_USD = 20_000


@dataclass
class MatchedMarket:
    market_id: str
    question: str
    slug: str
    end_date_utc: datetime
    yes_token_id: str
    no_token_id: str
    liquidity_usd: float
    raw: Dict[str, Any]

    def token_for_direction(self, direction: str) -> Optional[str]:
        d = (direction or "").lower()
        if d in ("up", "bull", "bullish", "yes", "long"):
            return self.yes_token_id
        if d in ("down", "bear", "bearish", "no", "short"):
            return self.no_token_id
        return None


class DailyBTCMarketMatcher:
    def __init__(
        self,
        client: Optional[PolymarketClient] = None,
        min_liquidity_usd: float = DEFAULT_MIN_LIQUIDITY_USD,
        slug_prefix: str = DAILY_BTC_SLUG_PREFIX,
    ):
        self.client = client or PolymarketClient()
        self.min_liquidity_usd = float(min_liquidity_usd)
        self.slug_prefix = slug_prefix

    # ------------------------------------------------------------------
    def find_market_for_anchor(
        self,
        anchor_utc: datetime,
        symbol: str = "BTC",
    ) -> Optional[MatchedMarket]:
        """Find the live daily market resolving at ``anchor_utc``.

        Returns ``None`` if no market passes all gates (slug / endDate /
        liquidity / token availability).
        """
        if symbol.upper() != "BTC":
            logger.info("matcher only supports BTC daily markets for now (got %s)", symbol)
            return None

        candidates = self.client.search_markets_by_slug_prefix(self.slug_prefix, limit=200)
        if not candidates:
            logger.warning("no candidates returned by Polymarket for prefix %s", self.slug_prefix)
            return None

        target = anchor_utc.astimezone(timezone.utc) if anchor_utc.tzinfo else anchor_utc.replace(tzinfo=timezone.utc)
        tolerance = timedelta(hours=END_DATE_TOLERANCE_HOURS)
        best: Optional[MatchedMarket] = None
        best_delta = tolerance + timedelta(seconds=1)

        for m in candidates:
            end_iso = m.get("endDate") or m.get("end_date_iso")
            if not end_iso:
                continue
            try:
                end_dt = datetime.fromisoformat(str(end_iso).replace("Z", "+00:00"))
            except ValueError:
                continue
            delta = abs(end_dt - target)
            if delta > tolerance or delta >= best_delta:
                continue
            if not _is_open(m):
                continue
            tokens = _extract_tokens(m)
            if not tokens:
                continue
            yes_tok, no_tok = tokens
            liquidity = _liquidity_usd(m)
            if liquidity < self.min_liquidity_usd:
                logger.info("market %s rejected: liquidity $%.0f < $%.0f", m.get("slug"), liquidity, self.min_liquidity_usd)
                continue
            best = MatchedMarket(
                market_id=str(m.get("id") or m.get("conditionId") or ""),
                question=str(m.get("question") or ""),
                slug=str(m.get("slug") or ""),
                end_date_utc=end_dt,
                yes_token_id=yes_tok,
                no_token_id=no_tok,
                liquidity_usd=liquidity,
                raw=m,
            )
            best_delta = delta
        return best

    # ------------------------------------------------------------------
    def find_resolved_market_for_anchor(
        self,
        anchor_utc: datetime,
        symbol: str = "BTC",
    ) -> Optional[MatchedMarket]:
        """Historical replay: find a closed market resolving at ``anchor_utc``."""
        m = self.client.find_resolved_market_at(anchor_utc, slug_pattern=self.slug_prefix)
        if not m:
            return None
        end_iso = m.get("endDate")
        try:
            end_dt = datetime.fromisoformat(str(end_iso).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        tokens = _extract_tokens(m)
        if not tokens:
            return None
        return MatchedMarket(
            market_id=str(m.get("id") or m.get("conditionId") or ""),
            question=str(m.get("question") or ""),
            slug=str(m.get("slug") or ""),
            end_date_utc=end_dt,
            yes_token_id=tokens[0],
            no_token_id=tokens[1],
            liquidity_usd=_liquidity_usd(m),
            raw=m,
        )


# ----------------------------------------------------------------------
def _is_open(m: Dict[str, Any]) -> bool:
    if m.get("closed") is True:
        return False
    if m.get("archived") is True:
        return False
    if m.get("active") is False:
        return False
    return True


def _liquidity_usd(m: Dict[str, Any]) -> float:
    for key in ("liquidity", "liquidityNum", "liquidity_usd"):
        v = m.get(key)
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return 0.0


def _extract_tokens(m: Dict[str, Any]):
    """Return (yes_token_id, no_token_id) or None."""
    tokens = m.get("clobTokenIds") or m.get("tokens") or m.get("outcomes")
    if isinstance(tokens, str):
        # Gamma sometimes serializes as a JSON string.
        import json as _json
        try:
            tokens = _json.loads(tokens)
        except Exception:
            return None
    if not isinstance(tokens, list) or len(tokens) < 2:
        return None
    # Outcomes order is usually [Yes, No]; verify when objects.
    yes_tok = no_tok = None
    if all(isinstance(t, dict) for t in tokens):
        for t in tokens:
            outcome = str(t.get("outcome") or t.get("name") or "").lower()
            tid = str(t.get("token_id") or t.get("tokenId") or t.get("id") or "")
            if not tid:
                continue
            if "yes" in outcome or outcome == "up":
                yes_tok = tid
            elif "no" in outcome or outcome == "down":
                no_tok = tid
    else:
        # Bare list of token ids — assume index 0 = Yes.
        yes_tok = str(tokens[0])
        no_tok = str(tokens[1])
    if not yes_tok or not no_tok:
        return None
    return yes_tok, no_tok
