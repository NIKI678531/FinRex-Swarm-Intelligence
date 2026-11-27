"""Weekly price-bin builder.

Mirrors the structure of Polymarket "what price will <asset> hit week X" markets:
a small set of mutually-exclusive price ranges with two open-ended tail bins.

Default: 7 buckets centered on `spot_price`.
    (-inf, -5%), (-5%, -2.5%), (-2.5%, -1%), (-1%, +1%),
    (+1%, +2.5%), (+2.5%, +5%), (+5%, +inf)

Bins are returned in canonical order (lowest to highest), each as
{ index, low, high, label }. `low=None` denotes -inf, `high=None` denotes +inf.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

# Centered offsets in fraction units: e.g. 0.025 = ±2.5% from spot.
DEFAULT_OFFSETS: Tuple[float, ...] = (0.05, 0.025, 0.01)


def build_weekly_bins(
    spot_price: float,
    *,
    offsets: Tuple[float, ...] = DEFAULT_OFFSETS,
) -> List[Dict[str, Any]]:
    if spot_price <= 0:
        raise ValueError("spot_price must be positive")
    if not offsets:
        raise ValueError("offsets must not be empty")

    sorted_off = sorted(offsets, reverse=True)  # descending: 0.05, 0.025, 0.01
    edges_low = [spot_price * (1.0 - o) for o in sorted_off]   # below spot
    edges_high = [spot_price * (1.0 + o) for o in reversed(sorted_off)]  # above spot, ascending

    bins: List[Dict[str, Any]] = []
    # tail-low bin: (-inf, edges_low[0])
    bins.append({"index": 0, "low": None, "high": round(edges_low[0], 2),
                 "label": f"< -{int(sorted_off[0]*100)}%"})
    # mid bins below spot
    for i in range(len(edges_low) - 1):
        bins.append({
            "index": len(bins),
            "low": round(edges_low[i], 2),
            "high": round(edges_low[i + 1], 2),
            "label": f"-{int(sorted_off[i]*100)}% ~ -{int(sorted_off[i+1]*100)}%",
        })
    # central bin around spot: (edges_low[-1], edges_high[0])
    bins.append({
        "index": len(bins),
        "low": round(edges_low[-1], 2),
        "high": round(edges_high[0], 2),
        "label": f"±{int(sorted_off[-1]*100)}%",
    })
    # mid bins above spot
    for i in range(len(edges_high) - 1):
        bins.append({
            "index": len(bins),
            "low": round(edges_high[i], 2),
            "high": round(edges_high[i + 1], 2),
            "label": f"+{int(reversed_offsets()[i]*100)}% ~ +{int(reversed_offsets()[i+1]*100)}%",
        })
    # tail-high bin
    bins.append({
        "index": len(bins),
        "low": round(edges_high[-1], 2),
        "high": None,
        "label": f"> +{int(sorted_off[0]*100)}%",
    })
    return bins


def reversed_offsets() -> Tuple[float, ...]:
    return tuple(sorted(DEFAULT_OFFSETS))


def assign_bin(price: float, bins: List[Dict[str, Any]]) -> Optional[int]:
    """Return the index of the bin containing `price`, or None if no match."""
    for b in bins:
        lo = b["low"]
        hi = b["high"]
        if (lo is None or price >= lo) and (hi is None or price < hi):
            return b["index"]
    # Edge case: price exactly equals upper-most edge → put in last bin.
    if bins and bins[-1]["high"] is not None and price == bins[-1]["high"]:
        return bins[-1]["index"]
    return None


# ----------------------------------------------------------------------
# Cycle helpers (Mon 00:00 UTC anchor → Sun 23:59 UTC resolve)
# ----------------------------------------------------------------------
def current_week_anchors(now: Optional[datetime] = None) -> Dict[str, datetime]:
    """Return {anchor, resolve, next_anchor} aligned to ISO week (Mon-Sun UTC)."""
    n = now or datetime.now(timezone.utc)
    if n.tzinfo is None:
        n = n.replace(tzinfo=timezone.utc)
    n = n.astimezone(timezone.utc)
    monday = (n - timedelta(days=n.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    sunday_end = monday + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return {
        "anchor": monday,
        "resolve": sunday_end,
        "next_anchor": monday + timedelta(days=7),
    }


def cycle_id(anchor: datetime) -> str:
    """Stable ISO-week id, e.g. '2026-W19'."""
    iso = anchor.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


# ----------------------------------------------------------------------
# Polymarket outcome alignment
# ----------------------------------------------------------------------
# Local weekly bins are RELATIVE percentage ranges around spot; Polymarket
# "what price will BTC hit" outcomes are ABSOLUTE price ranges. We align the two
# using a spot-scaled tolerance plus interval-overlap (IoU), and grade the match
# so the UI can be honest about alignment quality instead of silently pairing by
# index (which mis-pairs at BTC ~$100k where a flat $100 tolerance never holds).
MATCH_QUALITY_ORDER = ("exact", "approx", "fallback", "none")


def _edge_close(a: Optional[float], b: Optional[float], tol: float) -> bool:
    """Both open (None) → True. One open → False. Else within absolute `tol`."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def _interval_iou(
    a_low: Optional[float], a_high: Optional[float],
    b_low: Optional[float], b_high: Optional[float],
    *, span: float,
) -> float:
    """IoU of two ranges; open ends are clamped to a finite window of `span`."""
    lo_a = a_low if a_low is not None else (b_low if b_low is not None else 0.0) - span
    hi_a = a_high if a_high is not None else (b_high if b_high is not None else 0.0) + span
    lo_b = b_low if b_low is not None else lo_a - span
    hi_b = b_high if b_high is not None else hi_a + span
    inter = max(0.0, min(hi_a, hi_b) - max(lo_a, lo_b))
    union = max(hi_a, hi_b) - min(lo_a, lo_b)
    if union <= 0:
        return 0.0
    return inter / union


def match_polymarket_outcome(
    bin_row: Dict[str, Any],
    outcomes: List[Dict[str, Any]],
    *,
    spot: float,
    pct_tol: float = 0.003,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """Return (best_outcome, match_quality) for one local bin.

    quality:
        "exact"    — both edges within `pct_tol` of spot (≈0.3%).
        "approx"   — best interval-overlap IoU ≥ 0.5.
        "fallback" — index-aligned guess (low confidence; UI should flag).
        "none"     — nothing sensible to pair with.
    """
    if not outcomes:
        return None, "none"
    tol = max(1.0, abs(float(spot)) * float(pct_tol))
    span = max(1.0, abs(float(spot)) * 0.05)

    # 1) exact: both edges close.
    for outcome in outcomes:
        if _edge_close(outcome.get("low"), bin_row.get("low"), tol) and \
           _edge_close(outcome.get("high"), bin_row.get("high"), tol):
            return outcome, "exact"

    # 2) approx: best IoU above threshold.
    best_outcome = None
    best_iou = 0.0
    for outcome in outcomes:
        iou = _interval_iou(
            outcome.get("low"), outcome.get("high"),
            bin_row.get("low"), bin_row.get("high"),
            span=span,
        )
        if iou > best_iou:
            best_iou, best_outcome = iou, outcome
    if best_outcome is not None and best_iou >= 0.5:
        return best_outcome, "approx"

    # 3) fallback: index alignment (legacy behaviour, explicitly flagged).
    idx = int(bin_row.get("index", -1))
    if 0 <= idx < len(outcomes):
        return outcomes[idx], "fallback"
    return None, "none"
