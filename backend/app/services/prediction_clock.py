"""Prediction clock aligned to Polymarket daily BTC market resolution.

Polymarket's daily "Bitcoin Up or Down" markets resolve at 12:00 UTC each day
(20:00 Asia/Hong_Kong). Every forecast we generate must be tagged with the
exact UTC anchor it is meant to predict so that validation execution and
later settlement use a consistent time frame.

This module is intentionally dependency-free (stdlib only) so it can be
imported by both the forecast service and the validation engine without
introducing coupling.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

# Polymarket daily BTC markets resolve at 12:00 UTC.
POLYMARKET_DAILY_RESOLVE_UTC_HOUR = 12

# Default blackout window (minutes before resolve when we stop opening new positions).
DEFAULT_BLACKOUT_MINUTES = 30


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class CycleAnchors:
    """Snapshot of the prediction cycle relative to a `now` instant."""

    now: datetime
    current_resolve: datetime
    previous_resolve: datetime
    next_resolve: datetime
    seconds_to_resolve: int
    is_in_blackout: bool

    def as_dict(self) -> Dict[str, Any]:
        return {
            "generated_at": self.now.isoformat(),
            "resolve_anchor_utc": self.current_resolve.isoformat(),
            "previous_resolve_utc": self.previous_resolve.isoformat(),
            "next_resolve_utc": self.next_resolve.isoformat(),
            "time_to_resolve_seconds": self.seconds_to_resolve,
            "is_in_blackout": self.is_in_blackout,
            "valid_for_market": not self.is_in_blackout and self.seconds_to_resolve > 0,
        }


class PredictionClock:
    """Time-anchor utility aligned to Polymarket daily BTC resolves.

    Definitions:
      * "current resolve anchor" = the next 12:00 UTC instant >= now.
        That is the cycle the live forecast is predicting.
      * "previous resolve anchor" = current resolve - 24h.
      * "blackout window" = [resolve - blackout_minutes, resolve)
        During blackout the forecast is too close to settlement to act on.
    """

    def __init__(self, resolve_hour_utc: int = POLYMARKET_DAILY_RESOLVE_UTC_HOUR):
        if not 0 <= resolve_hour_utc <= 23:
            raise ValueError("resolve_hour_utc must be in [0, 23]")
        self.resolve_hour_utc = resolve_hour_utc

    # ------------------------------------------------------------------
    # Anchor computations
    # ------------------------------------------------------------------
    def current_resolve_anchor(self, now: Optional[datetime] = None) -> datetime:
        """Return the next 12:00 UTC instant >= now (the cycle being predicted).

        If `now` is exactly 12:00:00 UTC, that same instant is returned (the
        cycle is resolving right now). Any moment after that rolls forward
        24h to tomorrow's resolve.
        """
        n = self._normalize(now)
        anchor_today = n.replace(
            hour=self.resolve_hour_utc, minute=0, second=0, microsecond=0
        )
        if n <= anchor_today:
            return anchor_today
        return anchor_today + timedelta(days=1)

    def previous_resolve_anchor(self, now: Optional[datetime] = None) -> datetime:
        return self.current_resolve_anchor(now) - timedelta(days=1)

    def next_resolve_anchor(self, now: Optional[datetime] = None) -> datetime:
        return self.current_resolve_anchor(now) + timedelta(days=1)

    def time_to_resolve(self, now: Optional[datetime] = None) -> timedelta:
        n = self._normalize(now)
        return self.current_resolve_anchor(n) - n

    def is_in_blackout_window(
        self,
        now: Optional[datetime] = None,
        blackout_minutes: int = DEFAULT_BLACKOUT_MINUTES,
    ) -> bool:
        if blackout_minutes <= 0:
            return False
        ttr = self.time_to_resolve(now).total_seconds()
        # In blackout if 0 < ttr <= blackout window. ttr == 0 means resolve has hit.
        return 0 < ttr <= blackout_minutes * 60

    def snapshot(
        self,
        now: Optional[datetime] = None,
        blackout_minutes: int = DEFAULT_BLACKOUT_MINUTES,
    ) -> CycleAnchors:
        n = self._normalize(now)
        cur = self.current_resolve_anchor(n)
        ttr = int((cur - n).total_seconds())
        return CycleAnchors(
            now=n,
            current_resolve=cur,
            previous_resolve=cur - timedelta(days=1),
            next_resolve=cur + timedelta(days=1),
            seconds_to_resolve=ttr,
            is_in_blackout=self.is_in_blackout_window(n, blackout_minutes),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize(now: Optional[datetime]) -> datetime:
        if now is None:
            return _utcnow()
        if now.tzinfo is None:
            return now.replace(tzinfo=timezone.utc)
        return now.astimezone(timezone.utc)


# Module-level singleton for cheap access.
default_clock = PredictionClock()


def build_time_anchor(
    now: Optional[datetime] = None,
    blackout_minutes: int = DEFAULT_BLACKOUT_MINUTES,
) -> Dict[str, Any]:
    """Convenience wrapper used by the forecast service to attach a
    `time_anchor` block to every forecast payload."""
    return default_clock.snapshot(now=now, blackout_minutes=blackout_minutes).as_dict()
