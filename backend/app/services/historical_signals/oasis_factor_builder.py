"""OASIS crowd-intelligence factor extraction for financial backtests.

The simulation timeline is relative, so a supplied simulation is projected onto
the backtest window from `start_ts` onward. Missing or unavailable simulations
return neutral zero factors and explicit coverage metadata.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from ..oasis_action_loader import OasisActionLoader, OasisActionRecord


OASIS_FACTOR_KEYS = [
    "oasis_sentiment",
    "oasis_pulse_score",
    "oasis_risk_intensity",
    "oasis_volume_z",
    "oasis_velocity_z",
    "oasis_consensus",
    "oasis_disagreement",
    "oasis_cross_platform_spread",
    "oasis_fomo_score",
    "oasis_panic_score",
]

_POS = {
    "bull", "bullish", "buy", "moon", "rally", "breakout", "surge", "pump",
    "accumulate", "support", "strong", "recover", "upside", "long", "risk-on",
}
_NEG = {
    "bear", "bearish", "sell", "dump", "crash", "breakdown", "liquidation",
    "hack", "ban", "probe", "lawsuit", "panic", "weak", "downside", "short",
}
_RISK = {
    "risk", "regulator", "regulation", "sec", "lawsuit", "hack", "exploit", "halt",
    "delist", "liquidation", "default", "fraud", "bankrupt", "probe", "ban",
}
_FOMO = {"fomo", "moon", "ape", "breakout", "pump", "all in", "miss out", "new high", "ath"}
_PANIC = {"panic", "capitulate", "crash", "dump", "liquidation", "rekt", "fear", "selloff"}
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z\-']+|[\u4e00-\u9fff]+")


def neutral_oasis_factors() -> Dict[str, float]:
    return {key: 0.0 for key in OASIS_FACTOR_KEYS}


def _contains(text: str, terms: Iterable[str]) -> int:
    low = text.lower()
    return sum(1 for term in terms if term in low)


def _sentiment(text: str, action_type: str = "") -> float:
    if not text and not action_type:
        return 0.0
    pos = _contains(text, _POS)
    neg = _contains(text, _NEG)
    action = action_type.lower()
    if any(k in action for k in ("like", "follow", "repost", "share")):
        pos += 0.5
    if any(k in action for k in ("unlike", "block", "delete", "report")):
        neg += 0.5
    total = pos + neg
    return 0.0 if total <= 0 else max(-1.0, min(1.0, (pos - neg) / total))


def _stance(sentiment: float) -> str:
    if sentiment > 0.15:
        return "bullish"
    if sentiment < -0.15:
        return "bearish"
    return "neutral"


def _std(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(max(0.0, var))


def _z_map(values_by_day: Dict[str, float]) -> Dict[str, float]:
    values = list(values_by_day.values())
    if not values:
        return {}
    mean = sum(values) / len(values)
    sd = _std(values)
    if sd == 0:
        return {day: 0.0 for day in values_by_day}
    return {day: (value - mean) / sd for day, value in values_by_day.items()}


def _day_for_record(record: OasisActionRecord, start_ts: datetime) -> str:
    if start_ts.tzinfo is None:
        start_ts = start_ts.replace(tzinfo=timezone.utc)
    hour = record.simulated_hour
    if hour is None:
        hour = max(0, record.round_num) * 1.0
    dt = start_ts + timedelta(hours=max(0.0, float(hour)))
    return dt.strftime("%Y-%m-%d")


def build_oasis_daily_factors(
    simulation_id: Optional[str],
    start_ts: datetime,
    end_ts: datetime,
) -> Dict[str, Any]:
    """Return `{rows_by_date, coverage}` for OASIS-derived daily factors."""
    bundle = OasisActionLoader.load(simulation_id)
    if not simulation_id or not bundle.actions:
        return {
            "rows_by_date": {},
            "coverage": {
                "simulation_id": simulation_id,
                "available": False,
                "action_count": 0,
                "covered_days": 0,
                "reason": "missing_or_empty_oasis_stream",
            },
        }

    if end_ts.tzinfo is None:
        end_ts = end_ts.replace(tzinfo=timezone.utc)
    buckets: Dict[str, List[OasisActionRecord]] = defaultdict(list)
    for record in bundle.actions:
        day = _day_for_record(record, start_ts)
        if day <= end_ts.strftime("%Y-%m-%d"):
            buckets[day].append(record)

    raw_rows: Dict[str, Dict[str, float]] = {}
    volumes: Dict[str, float] = {}
    previous_volume = 0.0
    for day in sorted(buckets):
        records = buckets[day]
        sentiments = [_sentiment(r.text, r.action_type) for r in records]
        stances = Counter(_stance(s) for s in sentiments)
        active_agents = {r.agent_id for r in records if r.agent_id is not None}
        platforms = {r.platform for r in records if r.platform}
        texts = "\n".join(r.text for r in records if r.text)
        volume = float(len(records))
        volumes[day] = volume

        max_stance = max(stances.values()) if stances else 0
        consensus = max_stance / max(1, len(records))
        disagreement = 1.0 - consensus if records else 0.0
        risk = min(1.0, _contains(texts, _RISK) * 0.18 + stances.get("bearish", 0) / max(1, len(records)) * 0.35)
        fomo = min(1.0, _contains(texts, _FOMO) * 0.18 + stances.get("bullish", 0) / max(1, len(records)) * 0.25)
        panic = min(1.0, _contains(texts, _PANIC) * 0.20 + stances.get("bearish", 0) / max(1, len(records)) * 0.25)
        platform_spread = min(1.0, len(platforms) / 2.0)
        velocity = volume - previous_volume
        previous_volume = volume

        raw_rows[day] = {
            "oasis_sentiment": round(sum(sentiments) / max(1, len(sentiments)), 4),
            "oasis_pulse_score": 0.0,  # filled after volume/velocity normalization
            "oasis_risk_intensity": round(risk, 4),
            "oasis_volume_z": 0.0,
            "oasis_velocity_z": velocity,
            "oasis_consensus": round(consensus, 4),
            "oasis_disagreement": round(disagreement, 4),
            "oasis_cross_platform_spread": round(platform_spread, 4),
            "oasis_fomo_score": round(fomo, 4),
            "oasis_panic_score": round(panic, 4),
            "oasis_action_count": volume,
            "oasis_active_agents": float(len(active_agents)),
        }

    volume_z = _z_map(volumes)
    velocity_z = _z_map({day: row["oasis_velocity_z"] for day, row in raw_rows.items()})
    for day, row in raw_rows.items():
        row["oasis_volume_z"] = round(volume_z.get(day, 0.0), 4)
        row["oasis_velocity_z"] = round(velocity_z.get(day, 0.0), 4)
        pulse = (
            0.24 * max(0.0, row["oasis_volume_z"])
            + 0.22 * max(0.0, row["oasis_velocity_z"])
            + 0.18 * abs(row["oasis_sentiment"])
            + 0.16 * row["oasis_risk_intensity"]
            + 0.10 * row["oasis_cross_platform_spread"]
            + 0.10 * row["oasis_disagreement"]
        )
        row["oasis_pulse_score"] = round(max(0.0, min(1.0, pulse)), 4)

    return {
        "rows_by_date": raw_rows,
        "coverage": {
            "simulation_id": simulation_id,
            "available": True,
            "action_count": len(bundle.actions),
            "covered_days": len(raw_rows),
            "files_read": bundle.files_read,
            "bad_lines": bundle.bad_lines,
        },
    }


class OasisFactorBuilder:
    """Small wrapper class for callers that prefer object-style dependency injection."""

    factor_keys = OASIS_FACTOR_KEYS

    @staticmethod
    def neutral() -> Dict[str, float]:
        return neutral_oasis_factors()

    @staticmethod
    def build_daily(
        simulation_id: Optional[str],
        start_ts: datetime,
        end_ts: datetime,
    ) -> Dict[str, Any]:
        return build_oasis_daily_factors(simulation_id, start_ts, end_ts)
