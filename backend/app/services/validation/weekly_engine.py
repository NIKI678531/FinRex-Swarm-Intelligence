"""Weekly validation engine — cycle, forecast, virtual betting, settlement.

Uses SQLAlchemy tables prefixed with `wk_*` in the shared validation store.

Virtual market rules:
- Bins are mutually exclusive. Polymarket yes price is used as entry
  probability when available; otherwise a uniform 1/n baseline is used.
- Edge per bin = model_prob - entry_prob.
- Stake uses capped fractional Kelly and the total paper stake never exceeds
  `max_stake_pct` of cash.
- Payout if hit = stake / entry_prob, so positive model edge has positive EV.
- All bets are paid in/out at resolve from the cycle's `cash_pool` so PnL
  is well-defined without an external order book.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text,
    inspect, text,
)
from sqlalchemy.orm import relationship

from ...config import Config
from ...repositories.validation_store import Base, _iso, _utcnow, get_engine, get_session
from ..historical_signals import data_loader_market
from ..model_config import get_active_strategy_cfg
from .weekly_bins import (
    assign_bin, build_weekly_bins, current_week_anchors, cycle_id as _cycle_id,
    match_polymarket_outcome,
)
from .weekly_forecast import fetch_spot_price, forecast_weekly_distribution
from .model_registry import resolve_model, DEFAULT_MODEL_KEY

logger = logging.getLogger("finrex.validation.engine")


# ----------------------------------------------------------------------
# Models (tables prefixed wk_)
# ----------------------------------------------------------------------
class WeeklyCycle(Base):
    __tablename__ = "wk_cycles"

    id = Column(Integer, primary_key=True)
    cycle_id = Column(String(16), nullable=False, unique=True, index=True)  # "2026-W19"
    symbol = Column(String(16), nullable=False, index=True)
    anchor_utc = Column(DateTime, nullable=False)
    resolve_utc = Column(DateTime, nullable=False, index=True)
    spot_at_anchor = Column(Float, nullable=False)
    bins = Column(JSON, nullable=False)
    status = Column(String(16), nullable=False, default="open", index=True)  # open / settled
    realized_close = Column(Float, nullable=True)
    realized_bin_index = Column(Integer, nullable=True)
    settled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    forecasts = relationship("WeeklyForecast", back_populates="cycle", cascade="all, delete-orphan")
    positions = relationship("WeeklyPosition", back_populates="cycle", cascade="all, delete-orphan")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "cycle_id": self.cycle_id,
            "symbol": self.symbol,
            "anchor_utc": _iso(self.anchor_utc),
            "resolve_utc": _iso(self.resolve_utc),
            "spot_at_anchor": self.spot_at_anchor,
            "bins": self.bins,
            "status": self.status,
            "realized_close": self.realized_close,
            "realized_bin_index": self.realized_bin_index,
            "settled_at": _iso(self.settled_at),
            "created_at": _iso(self.created_at),
        }


class WeeklyForecast(Base):
    __tablename__ = "wk_forecasts"

    id = Column(Integer, primary_key=True)
    cycle_db_id = Column(Integer, ForeignKey("wk_cycles.id"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    bins_probs = Column(JSON, nullable=False)        # [{index, low, high, prob, count}]
    expected_price = Column(Float, nullable=True)
    median_price = Column(Float, nullable=True)
    n_paths = Column(Integer, nullable=False)
    model_family = Column(String(48), nullable=True, index=True)
    payload = Column(JSON, nullable=False)            # full forecast debug payload

    cycle = relationship("WeeklyCycle", back_populates="forecasts")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "cycle_db_id": self.cycle_db_id,
            "created_at": _iso(self.created_at),
            "bins_probs": self.bins_probs,
            "expected_price": self.expected_price,
            "median_price": self.median_price,
            "n_paths": self.n_paths,
            "model_family": self.model_family,
            "payload": self.payload,
        }


class WeeklyPosition(Base):
    __tablename__ = "wk_positions"

    id = Column(Integer, primary_key=True)
    cycle_db_id = Column(Integer, ForeignKey("wk_cycles.id"), nullable=False, index=True)
    forecast_id = Column(Integer, ForeignKey("wk_forecasts.id"), nullable=True)
    bin_index = Column(Integer, nullable=False)
    bin_low = Column(Float, nullable=True)
    bin_high = Column(Float, nullable=True)
    bin_label = Column(String(64), nullable=True)
    model_prob = Column(Float, nullable=False)
    baseline_prob = Column(Float, nullable=False)
    market_prob = Column(Float, nullable=True)
    probability_source = Column(String(32), nullable=True)
    match_quality = Column(String(16), nullable=True)
    edge = Column(Float, nullable=False)
    edge_vs_market = Column(Float, nullable=True)
    edge_vs_baseline = Column(Float, nullable=True)
    kelly_fraction_raw = Column(Float, nullable=True)
    final_stake_fraction = Column(Float, nullable=True)
    stake = Column(Float, nullable=False)
    payout_if_hit = Column(Float, nullable=False)
    expected_value = Column(Float, nullable=True)
    is_hit = Column(Boolean, nullable=True)
    realized_pnl = Column(Float, nullable=True)
    opened_at = Column(DateTime, nullable=False, default=_utcnow)
    settled_at = Column(DateTime, nullable=True)

    cycle = relationship("WeeklyCycle", back_populates="positions")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "cycle_db_id": self.cycle_db_id,
            "forecast_id": self.forecast_id,
            "bin_index": self.bin_index,
            "bin_range": [self.bin_low, self.bin_high],
            "bin_label": self.bin_label,
            "model_prob": self.model_prob,
            "baseline_prob": self.baseline_prob,
            "market_prob": self.market_prob,
            "probability_source": self.probability_source,
            "match_quality": self.match_quality,
            "edge": self.edge,
            "edge_vs_market": self.edge_vs_market,
            "edge_vs_baseline": self.edge_vs_baseline,
            "kelly_fraction_raw": self.kelly_fraction_raw,
            "final_stake_fraction": self.final_stake_fraction,
            "stake": self.stake,
            "payout_if_hit": self.payout_if_hit,
            "expected_value": self.expected_value,
            "is_hit": self.is_hit,
            "realized_pnl": self.realized_pnl,
            "opened_at": _iso(self.opened_at),
            "settled_at": _iso(self.settled_at),
        }


# Make sure tables exist on first import, even if the shared engine was already
# created before weekly models were imported.
Base.metadata.create_all(get_engine())


def _ensure_weekly_schema() -> None:
    engine = get_engine()
    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    if "wk_positions" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("wk_positions")}
    additions = {
        "market_prob": "FLOAT",
        "probability_source": "VARCHAR(32)",
        "match_quality": "VARCHAR(16)",
        "kelly_fraction_raw": "FLOAT",
        "final_stake_fraction": "FLOAT",
        "expected_value": "FLOAT",
        "edge_vs_market": "FLOAT",
        "edge_vs_baseline": "FLOAT",
    }
    with engine.begin() as conn:
        for name, ddl in additions.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE wk_positions ADD COLUMN {name} {ddl}"))
    # wk_forecasts: model_family column
    if "wk_forecasts" in inspector.get_table_names():
        fc_existing = {col["name"] for col in inspector.get_columns("wk_forecasts")}
        if "model_family" not in fc_existing:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE wk_forecasts ADD COLUMN model_family VARCHAR(48)"))


_ensure_weekly_schema()


# ----------------------------------------------------------------------
# Engine entrypoints
# ----------------------------------------------------------------------
DEFAULT_SYMBOL = "BTC"


def _kelly_stake(model_prob: float, entry_prob: float, kelly_fraction: float) -> float:
    """Standard fractional binary Kelly for buying a YES share.

    A YES share bought at price `entry_prob` pays $1 if the bin resolves true.
    Net odds b = (1 - entry_prob) / entry_prob. With model win-prob p and
    q = 1 - p, the full-Kelly fraction is:

        f* = (b·p − q) / b = p − (1 − p)·entry_prob / (1 − entry_prob)

    Returns the unscaled fraction after applying `kelly_fraction`, clipped
    to [0, 1]. (Still to be capped by `max_stake_pct` across all bins.)
    """
    p = float(model_prob)
    q = 1.0 - p
    if entry_prob <= 0 or entry_prob >= 1 or p <= 0:
        return 0.0
    b = (1.0 - entry_prob) / entry_prob
    if b <= 0:
        return 0.0
    f_star = (b * p - q) / b
    if f_star <= 0:
        return 0.0
    return max(0.0, min(1.0, f_star * kelly_fraction))


def build_weekly_stake_decisions(
    forecast_bins: List[Dict[str, Any]],
    market_probs: Dict[int, Dict[str, Any]],
    *,
    baseline_prob: float,
    kelly_fraction: float,
    max_stake_pct: float,
    cash: float,
    min_edge: float = 0.0,
    fee_pct: float = 0.0,
    half_spread_pct: float = 0.0,
) -> List[Dict[str, Any]]:
    """Convert weekly probabilities into capped paper-bet decisions.

    Edge is reported on two explicit bases so the desk never conflates them:
      - `edge_vs_market`  = model_prob − market_yes_price  (only when real odds exist)
      - `edge_vs_baseline`= model_prob − uniform 1/n baseline
    The Kelly stake and gating use the *net* edge against whichever entry price
    is in force, after subtracting transaction cost (fee + half spread).
    """
    cost = float(fee_pct) + float(half_spread_pct)
    candidates: List[Dict[str, Any]] = []
    for b in forecast_bins:
        idx = int(b["index"])
        market_entry = market_probs.get(idx) or {}
        entry_prob_raw = market_entry.get("prob")
        has_market = entry_prob_raw is not None
        entry_prob = float(entry_prob_raw) if has_market else float(baseline_prob)
        prob_source = str(market_entry.get("source") or "uniform_baseline")
        match_quality = str(market_entry.get("match_quality") or ("polymarket" if has_market else "uniform_baseline"))
        model_prob = float(b.get("prob") or 0.0)

        edge_vs_baseline = model_prob - float(baseline_prob)
        edge_vs_market = (model_prob - float(entry_prob_raw)) if has_market else None
        gross_edge = model_prob - entry_prob
        net_edge = gross_edge - cost
        if net_edge < float(min_edge):
            continue
        raw_frac = _kelly_stake(model_prob, entry_prob, kelly_fraction)
        if raw_frac <= 0:
            continue
        candidates.append({
            "bin": b,
            "edge": gross_edge,
            "net_edge": net_edge,
            "edge_vs_market": edge_vs_market,
            "edge_vs_baseline": edge_vs_baseline,
            "raw_frac": raw_frac,
            "frac": raw_frac,
            "entry_prob": entry_prob,
            "prob_source": prob_source,
            "match_quality": match_quality,
            "has_market": has_market,
            "market_meta": market_entry,
        })

    total_frac = sum(s["frac"] for s in candidates) or 0.0
    if max_stake_pct >= 0 and total_frac > max_stake_pct:
        scale = max_stake_pct / total_frac if total_frac > 0 else 0.0
        for s in candidates:
            s["frac"] *= scale

    decisions: List[Dict[str, Any]] = []
    for s in candidates:
        stake_usd = round(float(cash) * float(s["frac"]), 2)
        if stake_usd <= 0:
            continue
        entry_prob = float(s["entry_prob"])
        payout = round(stake_usd / entry_prob, 2) if entry_prob > 0 else stake_usd
        expected_value = round(float(s["bin"].get("prob") or 0.0) * payout - stake_usd, 4)
        decisions.append({
            **s,
            "stake_usd": stake_usd,
            "payout_if_hit": payout,
            "expected_value": expected_value,
        })
    return decisions


def _ensure_cycle(symbol: str, now: Optional[datetime] = None) -> WeeklyCycle:
    """Get or create the current week's cycle."""
    anchors = current_week_anchors(now)
    cid = _cycle_id(anchors["anchor"])
    session = get_session()
    try:
        existing = session.query(WeeklyCycle).filter(
            WeeklyCycle.cycle_id == cid, WeeklyCycle.symbol == symbol
        ).first()
        if existing:
            return existing

        spot = fetch_spot_price(symbol)
        if spot is None:
            raise RuntimeError(f"no spot price available for {symbol}")
        bins = build_weekly_bins(spot)
        cycle = WeeklyCycle(
            cycle_id=cid,
            symbol=symbol,
            anchor_utc=anchors["anchor"],
            resolve_utc=anchors["resolve"],
            spot_at_anchor=spot,
            bins=bins,
            status="open",
        )
        session.add(cycle)
        session.commit()
        logger.info("created weekly cycle %s symbol=%s spot=%.2f", cid, symbol, spot)
        return cycle
    finally:
        session.close()


def get_or_create_current_cycle(symbol: str = DEFAULT_SYMBOL) -> Dict[str, Any]:
    cycle = _ensure_cycle(symbol)
    return _serialize_cycle(cycle.id)


def _weekly_market_probability_map(cycle: WeeklyCycle) -> Dict[int, Dict[str, Any]]:
    """Map local weekly bins to Polymarket outcome probabilities when available.

    Uses spot-scaled tolerance + interval-overlap matching (see
    `weekly_bins.match_polymarket_outcome`) and records the resulting
    `match_quality` so the UI can be honest about alignment confidence.
    """
    try:
        from ..polymarket.weekly_range_matcher import WeeklyBTCMarketMatcher
        payload = WeeklyBTCMarketMatcher().weekly_payload(mode="current", limit=1)
        outcomes = ((payload.get("current") or {}).get("outcomes") or []) if isinstance(payload, dict) else []
    except Exception as exc:  # noqa: BLE001
        logger.info("weekly Polymarket price unavailable: %s", exc)
        outcomes = []
    out: Dict[int, Dict[str, Any]] = {}
    spot = float(getattr(cycle, "spot_at_anchor", 0.0) or 0.0)
    for bin_row in cycle.bins or []:
        match, quality = match_polymarket_outcome(bin_row, outcomes, spot=spot)
        # Only "exact"/"approx" matches feed real market odds; "fallback" is too
        # unreliable to treat as a real price, so we surface it without a price.
        if match and match.get("yes_price") is not None and quality in ("exact", "approx"):
            out[int(bin_row["index"])] = {
                "prob": float(match["yes_price"]),
                "source": "polymarket_yes",
                "match_quality": quality,
                "label": match.get("label"),
                "token_id": match.get("token_id"),
            }
        elif match is not None:
            out[int(bin_row["index"])] = {
                "prob": None,
                "source": "polymarket_unmatched",
                "match_quality": quality,
                "label": match.get("label"),
            }
    return out


def _serialize_cycle(cycle_db_id: int) -> Dict[str, Any]:
    session = get_session()
    try:
        cycle = session.query(WeeklyCycle).filter(WeeklyCycle.id == cycle_db_id).first()
        if cycle is None:
            return {}
        latest_forecast = (
            session.query(WeeklyForecast)
            .filter(WeeklyForecast.cycle_db_id == cycle.id)
            .order_by(WeeklyForecast.created_at.desc())
            .first()
        )
        positions = (
            session.query(WeeklyPosition)
            .filter(WeeklyPosition.cycle_db_id == cycle.id)
            .order_by(WeeklyPosition.bin_index.asc())
            .all()
        )
        out = cycle.to_dict()
        now = datetime.now(timezone.utc)
        ttr = max(0, int((cycle.resolve_utc.replace(tzinfo=timezone.utc) - now).total_seconds())) if cycle.resolve_utc else 0
        out["time_to_resolve_seconds"] = ttr
        out["latest_forecast"] = latest_forecast.to_dict() if latest_forecast else None
        out["positions"] = [p.to_dict() for p in positions]
        return out
    finally:
        session.close()


def run_snapshot(
    symbol: str = DEFAULT_SYMBOL,
    *,
    n_paths: int = 5000,
    place_bets: bool = True,
    model_family: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a fresh forecast for the current cycle and (optionally) open bets."""
    cycle = _ensure_cycle(symbol)
    model_key = resolve_model(model_family)["key"]
    forecast = forecast_weekly_distribution(
        symbol,
        spot_price=cycle.spot_at_anchor,
        bins=cycle.bins,
        anchor_date=cycle.anchor_utc.replace(tzinfo=timezone.utc),
        n_paths=n_paths,
        model_family=model_key,
    )

    session = get_session()
    try:
        wf = WeeklyForecast(
            cycle_db_id=cycle.id,
            bins_probs=forecast["bins"],
            expected_price=forecast["expected_price"],
            median_price=forecast["median_price"],
            n_paths=forecast["n_paths"],
            model_family=model_key,
            payload=forecast,
        )
        session.add(wf)
        session.flush()
        forecast_id = wf.id

        opened = []
        if place_bets and cycle.status == "open":
            cfg = get_active_strategy_cfg(symbol)
            kelly_fraction = float(cfg.get("kelly_fraction", 0.25))
            max_stake_pct = float(cfg.get("max_position_pct", 0.05))
            cash = float(Config.VALIDATION_INITIAL_CAPITAL)
            n_bins = len(cycle.bins)
            baseline = 1.0 / n_bins if n_bins else 0.0
            market_probs = _weekly_market_probability_map(cycle)

            # Skip if we already have positions for this cycle (avoid double bets).
            existing = session.query(WeeklyPosition).filter(WeeklyPosition.cycle_db_id == cycle.id).count()
            if existing == 0:
                stakes = build_weekly_stake_decisions(
                    forecast["bins"],
                    market_probs,
                    baseline_prob=baseline,
                    kelly_fraction=kelly_fraction,
                    max_stake_pct=max_stake_pct,
                    cash=cash,
                    min_edge=float(Config.VALIDATION_MIN_EDGE),
                    fee_pct=float(Config.VALIDATION_POLY_FEE_PCT),
                    half_spread_pct=float(Config.VALIDATION_POLY_HALF_SPREAD_PCT),
                )
                for s in stakes:
                    pos = WeeklyPosition(
                        cycle_db_id=cycle.id,
                        forecast_id=forecast_id,
                        bin_index=s["bin"]["index"],
                        bin_low=s["bin"].get("low"),
                        bin_high=s["bin"].get("high"),
                        bin_label=s["bin"].get("label"),
                        model_prob=float(s["bin"]["prob"]),
                        baseline_prob=baseline,
                        market_prob=s["entry_prob"] if s.get("has_market") else None,
                        probability_source=s["prob_source"],
                        match_quality=s.get("match_quality"),
                        edge=s["edge"],
                        edge_vs_market=s.get("edge_vs_market"),
                        edge_vs_baseline=s.get("edge_vs_baseline"),
                        kelly_fraction_raw=s["raw_frac"],
                        final_stake_fraction=s["frac"],
                        stake=s["stake_usd"],
                        payout_if_hit=s["payout_if_hit"],
                        expected_value=s["expected_value"],
                    )
                    session.add(pos)
                    opened.append(pos)

        session.commit()
        logger.info("snapshot cycle=%s model=%s forecast=%d opened=%d",
                    cycle.cycle_id, model_key, forecast_id, len(opened))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    return _serialize_cycle(cycle.id)


def settle_due_cycles(symbol: str = DEFAULT_SYMBOL, *, force: bool = False) -> List[Dict[str, Any]]:
    """Settle any open cycles whose `resolve_utc` has passed."""
    now = datetime.now(timezone.utc)
    session = get_session()
    settled: List[Dict[str, Any]] = []
    try:
        q = session.query(WeeklyCycle).filter(
            WeeklyCycle.status == "open", WeeklyCycle.symbol == symbol,
        )
        if not force:
            q = q.filter(WeeklyCycle.resolve_utc <= now.replace(tzinfo=None))
        cycles = q.all()
        for cycle in cycles:
            close_price = _fetch_resolve_close(symbol, cycle.resolve_utc.replace(tzinfo=timezone.utc))
            if close_price is None:
                logger.warning("no close price yet for cycle %s; skipping", cycle.cycle_id)
                continue
            idx = assign_bin(close_price, cycle.bins)
            cycle.realized_close = close_price
            cycle.realized_bin_index = idx
            cycle.status = "settled"
            cycle.settled_at = datetime.now(timezone.utc)

            for pos in session.query(WeeklyPosition).filter(WeeklyPosition.cycle_db_id == cycle.id).all():
                pos.is_hit = (idx is not None and pos.bin_index == idx)
                pos.realized_pnl = round(pos.payout_if_hit - pos.stake, 2) if pos.is_hit else round(-pos.stake, 2)
                pos.settled_at = datetime.now(timezone.utc)
            session.commit()
            settled.append(cycle.to_dict())
            logger.info("settled cycle %s realized_close=%.2f bin=%s", cycle.cycle_id, close_price, idx)
        return settled
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _fetch_resolve_close(symbol: str, resolve_ts: datetime) -> Optional[float]:
    from datetime import timedelta as _td
    rows = data_loader_market.fetch_ohlcv(symbol, "1h", resolve_ts - _td(hours=6), resolve_ts + _td(hours=6))
    if not rows:
        return None
    # Find the bar closest to resolve_ts.
    best = min(rows, key=lambda r: abs(datetime.fromisoformat(r["ts"]) - resolve_ts))
    return float(best["close"])


# ----------------------------------------------------------------------
# Aggregations for the UI
# ----------------------------------------------------------------------
def list_positions(symbol: str = DEFAULT_SYMBOL, status: str = "all") -> List[Dict[str, Any]]:
    session = get_session()
    try:
        q = (
            session.query(WeeklyPosition, WeeklyCycle)
            .join(WeeklyCycle, WeeklyPosition.cycle_db_id == WeeklyCycle.id)
            .filter(WeeklyCycle.symbol == symbol)
            .order_by(WeeklyPosition.opened_at.desc())
        )
        if status == "open":
            q = q.filter(WeeklyCycle.status == "open")
        elif status == "settled":
            q = q.filter(WeeklyCycle.status == "settled")
        out: List[Dict[str, Any]] = []
        for pos, cycle in q.all():
            row = pos.to_dict()
            row["cycle_id"] = cycle.cycle_id
            row["resolve_utc"] = _iso(cycle.resolve_utc)
            row["status"] = cycle.status
            out.append(row)
        return out
    finally:
        session.close()


def kpi_summary(symbol: str = DEFAULT_SYMBOL) -> Dict[str, Any]:
    session = get_session()
    try:
        cycles = session.query(WeeklyCycle).filter(WeeklyCycle.symbol == symbol).all()
        positions = (
            session.query(WeeklyPosition)
            .join(WeeklyCycle, WeeklyPosition.cycle_db_id == WeeklyCycle.id)
            .filter(WeeklyCycle.symbol == symbol)
            .all()
        )
        total_stake = sum(p.stake or 0.0 for p in positions)
        realized = sum(p.realized_pnl or 0.0 for p in positions if p.realized_pnl is not None)
        n_settled = sum(1 for p in positions if p.is_hit is not None)
        wins = sum(1 for p in positions if p.is_hit)
        # Multi-class Brier across all settled cycles.
        brier_sum = 0.0
        n_brier = 0
        for cycle in cycles:
            if cycle.status != "settled" or cycle.realized_bin_index is None:
                continue
            forecast = (
                session.query(WeeklyForecast)
                .filter(WeeklyForecast.cycle_db_id == cycle.id)
                .order_by(WeeklyForecast.created_at.desc())
                .first()
            )
            if not forecast:
                continue
            for b in forecast.bins_probs:
                y = 1 if b["index"] == cycle.realized_bin_index else 0
                brier_sum += (b["prob"] - y) ** 2
                n_brier += 1
        equity = float(Config.VALIDATION_INITIAL_CAPITAL) + realized
        confidence_buckets = _confidence_buckets([p for p in positions if p.is_hit is not None])
        return {
            "n_cycles": len(cycles),
            "n_settled_cycles": sum(1 for c in cycles if c.status == "settled"),
            "n_positions": len(positions),
            "n_settled_positions": n_settled,
            "win_rate": round(wins / n_settled, 4) if n_settled else None,
            "total_stake": round(total_stake, 2),
            "realized_pnl": round(realized, 2),
            "equity": round(equity, 2),
            "multi_class_brier": round(brier_sum / n_brier, 4) if n_brier else None,
            "samples": n_brier,
            "confidence_buckets": confidence_buckets,
        }
    finally:
        session.close()


def _confidence_buckets(positions: List[WeeklyPosition]) -> List[Dict[str, Any]]:
    edges = [(0.0, 0.15), (0.15, 0.25), (0.25, 0.35), (0.35, 0.45), (0.45, 1.01)]
    out: List[Dict[str, Any]] = []
    for lo, hi in edges:
        rows = [p for p in positions if p.model_prob is not None and lo <= float(p.model_prob) < hi]
        if not rows:
            continue
        wins = sum(1 for p in rows if p.is_hit)
        pnl = sum(float(p.realized_pnl or 0.0) for p in rows)
        out.append({
            "bucket_low": lo,
            "bucket_high": hi if hi <= 1 else 1.0,
            "n": len(rows),
            "avg_model_prob": round(sum(float(p.model_prob or 0.0) for p in rows) / len(rows), 4),
            "win_rate": round(wins / len(rows), 4),
            "realized_pnl": round(pnl, 2),
        })
    return out


def equity_curve(symbol: str = DEFAULT_SYMBOL) -> List[Dict[str, Any]]:
    session = get_session()
    try:
        cycles = (
            session.query(WeeklyCycle)
            .filter(WeeklyCycle.symbol == symbol, WeeklyCycle.status == "settled")
            .order_by(WeeklyCycle.resolve_utc.asc())
            .all()
        )
        equity = float(Config.VALIDATION_INITIAL_CAPITAL)
        out: List[Dict[str, Any]] = []
        for cycle in cycles:
            pnl = sum(
                (p.realized_pnl or 0.0)
                for p in session.query(WeeklyPosition).filter(WeeklyPosition.cycle_db_id == cycle.id).all()
            )
            equity += pnl
            out.append({"ts": _iso(cycle.resolve_utc), "equity": round(equity, 2), "cycle_id": cycle.cycle_id})
        return out
    finally:
        session.close()
