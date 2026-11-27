"""Order book primitives for Polymarket CLOB.

Polymarket's CLOB is a binary outcome order book (asks for "Yes", bids for
"Yes"). Each fill consumes liquidity at successive ask levels — there is no
constant-product AMM curve. To accurately estimate the payout multiple of a
validation fill, we compute a volume-weighted average price (VWAP) by walking
the asks ladder.

Key invariants:
  * Asks are sorted ascending by price.
  * Bids are sorted descending by price.
  * Prices are decimals in [0, 1] (probability shares).
  * size is in number of shares (each share pays $1 if the outcome resolves YES).

Payout multiple = 1 / VWAP. A fill at avg price 0.55 returns 1/0.55 ≈ 1.818x
on success, 0 on failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class BookLevel:
    price: float  # share price in [0, 1]
    size: float  # shares available at this price


@dataclass
class OrderBook:
    """Snapshot of the CLOB book for one outcome token."""

    token_id: str
    asks: List[BookLevel] = field(default_factory=list)  # ascending
    bids: List[BookLevel] = field(default_factory=list)  # descending
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    @classmethod
    def from_clob(cls, token_id: str, payload: Dict[str, Any]) -> "OrderBook":
        """Parse the response of `GET /book?token_id=...` from the CLOB."""
        raw_asks = payload.get("asks") or []
        raw_bids = payload.get("bids") or []
        asks = [
            BookLevel(price=float(lvl["price"]), size=float(lvl["size"]))
            for lvl in raw_asks
            if _is_positive_level(lvl)
        ]
        bids = [
            BookLevel(price=float(lvl["price"]), size=float(lvl["size"]))
            for lvl in raw_bids
            if _is_positive_level(lvl)
        ]
        asks.sort(key=lambda x: x.price)
        bids.sort(key=lambda x: x.price, reverse=True)
        ts_raw = payload.get("timestamp")
        ts = _parse_ts(ts_raw)
        return cls(token_id=token_id, asks=asks, bids=bids, timestamp=ts)

    # ------------------------------------------------------------------
    # Top-of-book accessors
    # ------------------------------------------------------------------
    @property
    def best_ask(self) -> Optional[float]:
        return self.asks[0].price if self.asks else None

    @property
    def best_bid(self) -> Optional[float]:
        return self.bids[0].price if self.bids else None

    @property
    def midpoint(self) -> Optional[float]:
        if self.best_ask is None or self.best_bid is None:
            return self.best_ask if self.best_ask is not None else self.best_bid
        return (self.best_ask + self.best_bid) / 2.0

    @property
    def spread(self) -> Optional[float]:
        if self.best_ask is None or self.best_bid is None:
            return None
        return self.best_ask - self.best_bid

    # ------------------------------------------------------------------
    # VWAP simulation
    # ------------------------------------------------------------------
    def vwap_buy(self, usd: float) -> Tuple[Optional[float], float, float]:
        """Buy `usd` worth of YES shares walking the asks ladder.

        Returns ``(vwap, shares_filled, usd_unfilled)``.
        If the book is empty or has zero liquidity, vwap is None.
        """
        if usd <= 0:
            return None, 0.0, 0.0
        remaining_usd = float(usd)
        spent_usd = 0.0
        shares = 0.0
        for level in self.asks:
            if remaining_usd <= 1e-12:
                break
            level_notional = level.price * level.size
            if level_notional <= remaining_usd:
                spent_usd += level_notional
                shares += level.size
                remaining_usd -= level_notional
            else:
                # Partial fill
                fill_shares = remaining_usd / level.price
                spent_usd += remaining_usd
                shares += fill_shares
                remaining_usd = 0.0
        if shares <= 0:
            return None, 0.0, float(usd)
        vwap = spent_usd / shares
        return vwap, shares, remaining_usd

    def vwap_sell(self, shares: float) -> Tuple[Optional[float], float, float]:
        """Sell `shares` walking the bids ladder.

        Returns ``(vwap, usd_received, shares_unfilled)``.
        """
        if shares <= 0:
            return None, 0.0, 0.0
        remaining = float(shares)
        usd_received = 0.0
        sold = 0.0
        for level in self.bids:
            if remaining <= 1e-12:
                break
            take = min(level.size, remaining)
            usd_received += take * level.price
            sold += take
            remaining -= take
        if sold <= 0:
            return None, 0.0, float(shares)
        vwap = usd_received / sold
        return vwap, usd_received, remaining

    # ------------------------------------------------------------------
    # Diagnostics for the UI / execution gate
    # ------------------------------------------------------------------
    def slippage_pct(self, usd: float) -> Optional[float]:
        """Slippage of buying `usd` notional vs the current best ask.

        Returns positive percent (e.g. 0.0125 = 1.25% worse than best ask).
        """
        vwap, shares, unfilled = self.vwap_buy(usd)
        if vwap is None or self.best_ask is None or self.best_ask <= 0:
            return None
        return (vwap - self.best_ask) / self.best_ask

    def market_impact_curve(self, usd_max: float, steps: int = 20) -> List[Dict[str, Any]]:
        """Return ``steps`` (usd, vwap, shares, payout_multiple, slippage_bp)
        points showing how the fill price degrades with size.
        """
        if usd_max <= 0 or steps <= 0:
            return []
        ref = self.best_ask
        out: List[Dict[str, Any]] = []
        for i in range(1, steps + 1):
            usd = usd_max * (i / steps)
            vwap, shares, unfilled = self.vwap_buy(usd)
            if vwap is None:
                continue
            slip_bp = None
            if ref and ref > 0:
                slip_bp = round((vwap - ref) / ref * 10_000, 2)
            out.append({
                "usd": round(usd, 2),
                "vwap": round(vwap, 6),
                "shares": round(shares, 4),
                "payout_multiple": round(1.0 / vwap, 4) if vwap > 0 else None,
                "slippage_bp": slip_bp,
                "unfilled_usd": round(unfilled, 2),
            })
        return out

    def max_size_within_slippage(
        self,
        midpoint: Optional[float] = None,
        max_slippage_pct: float = 0.02,
    ) -> float:
        """Binary search for the largest USD notional whose VWAP slippage
        vs `midpoint` (or best_ask if None) stays within `max_slippage_pct`.

        Returns USD. Returns 0.0 if even the smallest meaningful trade
        exceeds the slippage cap.
        """
        if not self.asks:
            return 0.0
        ref = midpoint if midpoint is not None else self.best_ask
        if ref is None or ref <= 0:
            return 0.0
        # Upper bound = total ask notional.
        total_notional = sum(l.price * l.size for l in self.asks)
        if total_notional <= 0:
            return 0.0
        lo, hi = 0.0, total_notional
        # Quickly check if even the full book is within the cap.
        vwap_full, _, _ = self.vwap_buy(total_notional)
        if vwap_full is not None and (vwap_full - ref) / ref <= max_slippage_pct:
            return round(total_notional, 2)
        # Binary search.
        for _ in range(40):
            mid = (lo + hi) / 2.0
            vwap, _, _ = self.vwap_buy(mid)
            if vwap is None:
                lo = mid
                continue
            slip = (vwap - ref) / ref
            if slip <= max_slippage_pct:
                lo = mid
            else:
                hi = mid
        return round(lo, 2)

    # ------------------------------------------------------------------
    # Liquidity stats
    # ------------------------------------------------------------------
    def total_ask_notional(self) -> float:
        return float(sum(l.price * l.size for l in self.asks))

    def total_bid_notional(self) -> float:
        return float(sum(l.price * l.size for l in self.bids))


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _is_positive_level(lvl: Dict[str, Any]) -> bool:
    try:
        return float(lvl.get("price", 0)) > 0 and float(lvl.get("size", 0)) > 0
    except (TypeError, ValueError):
        return False


def _parse_ts(raw: Any) -> datetime:
    if raw is None:
        return datetime.now(timezone.utc)
    try:
        # Polymarket sometimes returns epoch ms as string.
        ts = float(raw)
        if ts > 1e12:
            ts = ts / 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except Exception:
            return datetime.now(timezone.utc)
