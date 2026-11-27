"""Model configuration registry — single source of truth for factor weights.

The Backtest Lab can promote a `BacktestRun` into an active `FactorWeightSet`.
The Validation Lab and on-line prediction code read the active set via
`get_active_factor_weights(symbol)` so improvements flow through automatically.

A built-in default is returned when no row is active, so callers never need
to special-case "first-run" state.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ..models.backtest import FactorWeightSet, get_session

logger = logging.getLogger("finrex.model_config")


# Built-in defaults: keep aligned with the factors that
# `services/public_opinion_service.py` and `time_pulse_model.py` consume.
DEFAULT_FACTOR_WEIGHTS: Dict[str, float] = {
    "sentiment_finbert": 0.30,
    "sentiment_emotion": 0.10,
    "news_volume": 0.10,
    "social_volume": 0.10,
    "price_momentum": 0.25,
    "volatility": 0.15,
    "oasis_sentiment": 0.12,
    "oasis_pulse_score": 0.10,
    "oasis_risk_intensity": -0.12,
    "oasis_volume_z": 0.06,
    "oasis_velocity_z": 0.06,
    "oasis_consensus": 0.08,
    "oasis_disagreement": -0.08,
    "oasis_cross_platform_spread": 0.05,
    "oasis_fomo_score": 0.06,
    "oasis_panic_score": -0.08,
}

DEFAULT_STRATEGY_CFG: Dict[str, Any] = {
    "horizon": "1d",
    "model_kind": "weighted",
    "ablation_mode": "market_text_oasis",
    "decision_threshold": 0.55,
    "entry_threshold": 0.55,
    "exit_threshold": 0.50,
    "execution_model": "markettime_long_cash",
    "execution_cfg": {
        "initial_capital": 10_000.0,
        "fix_reserve_ratio": 0.05,
        "trading_buy_cost_rate": 0.0003,
        "trading_sell_cost_rate": 0.0003,
        "transaction_fee_rate": 0.0,
        "slippage_rate": 0.0005,
        "asset_lot_size": 0.0001,
        "annual_holding_fee_rate": 0.0,
        "annual_periods": 365,
    },
    "kelly_fraction": 0.25,
    "max_position_pct": 0.05,
}


def get_active_factor_weights(symbol: str) -> Dict[str, float]:
    """Return the active weights for `symbol`, falling back to defaults."""
    session = get_session()
    try:
        row = (
            session.query(FactorWeightSet)
            .filter(FactorWeightSet.symbol == symbol, FactorWeightSet.is_active.is_(True))
            .first()
        )
        if row and isinstance(row.weights, dict) and row.weights:
            merged = dict(DEFAULT_FACTOR_WEIGHTS)
            merged.update(row.weights)
            return merged
        return dict(DEFAULT_FACTOR_WEIGHTS)
    finally:
        session.close()


def get_active_strategy_cfg(symbol: str) -> Dict[str, Any]:
    session = get_session()
    try:
        row = (
            session.query(FactorWeightSet)
            .filter(FactorWeightSet.symbol == symbol, FactorWeightSet.is_active.is_(True))
            .first()
        )
        if row and isinstance(row.strategy_cfg, dict) and row.strategy_cfg:
            merged = dict(DEFAULT_STRATEGY_CFG)
            merged.update(row.strategy_cfg)
            merged["execution_cfg"] = {
                **(DEFAULT_STRATEGY_CFG.get("execution_cfg") or {}),
                **(row.strategy_cfg.get("execution_cfg") or {}),
            }
            return merged
        return dict(DEFAULT_STRATEGY_CFG)
    finally:
        session.close()


def get_active_set(symbol: str) -> Optional[Dict[str, Any]]:
    session = get_session()
    try:
        row = (
            session.query(FactorWeightSet)
            .filter(FactorWeightSet.symbol == symbol, FactorWeightSet.is_active.is_(True))
            .first()
        )
        return row.to_dict() if row else None
    finally:
        session.close()


def list_sets(symbol: Optional[str] = None) -> list[Dict[str, Any]]:
    session = get_session()
    try:
        q = session.query(FactorWeightSet)
        if symbol:
            q = q.filter(FactorWeightSet.symbol == symbol)
        rows = q.order_by(FactorWeightSet.created_at.desc()).all()
        return [r.to_dict() for r in rows]
    finally:
        session.close()


def create_set(
    *,
    name: str,
    symbol: str,
    weights: Dict[str, float],
    strategy_cfg: Optional[Dict[str, Any]] = None,
    description: Optional[str] = None,
    model_version: str = "v1.0",
    created_from_run_id: Optional[int] = None,
    activate: bool = False,
) -> Dict[str, Any]:
    session = get_session()
    try:
        row = FactorWeightSet(
            name=name,
            symbol=symbol,
            model_version=model_version,
            weights=weights,
            strategy_cfg=strategy_cfg,
            description=description,
            created_from_run_id=created_from_run_id,
            is_active=False,
        )
        session.add(row)
        session.flush()
        if activate:
            _activate_locked(session, row)
        session.commit()
        return row.to_dict()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def set_active(set_id: int) -> Dict[str, Any]:
    session = get_session()
    try:
        row = session.query(FactorWeightSet).filter(FactorWeightSet.id == set_id).first()
        if row is None:
            raise ValueError(f"FactorWeightSet {set_id} not found")
        _activate_locked(session, row)
        session.commit()
        logger.info("Activated FactorWeightSet id=%s symbol=%s", row.id, row.symbol)
        return row.to_dict()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _activate_locked(session, row: FactorWeightSet) -> None:
    """Deactivate any other active set for this symbol, then activate `row`."""
    session.query(FactorWeightSet).filter(
        FactorWeightSet.symbol == row.symbol,
        FactorWeightSet.id != row.id,
        FactorWeightSet.is_active.is_(True),
    ).update({"is_active": False}, synchronize_session=False)
    row.is_active = True
    row.activated_at = datetime.now(timezone.utc)
