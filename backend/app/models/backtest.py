"""SQLAlchemy models for persisted historical backtest metadata.

Tables prefixed `bt_` so they live alongside validation records in the shared
SQLite file (see `Config.VALIDATION_DB_URL`) but are clearly separated.

Design contract:
- `BacktestRun` is the single source of truth for one backtest execution.
- `BacktestPrediction` stores per-step predictions vs realized outcomes.
- `FactorWeightSet` is the cross-cutting "model config" registry; the
  validation lab and on-line forecasting both read whichever row has
  `is_active=True` for a given symbol.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text,
    inspect, text,
)
from sqlalchemy.orm import relationship

# Reuse the same Base + engine factory so a single SQLite file holds both
# validation and backtest metadata.
from ..repositories.validation_store import Base, get_engine, get_session, _iso, _utcnow  # noqa: F401


class FactorWeightSet(Base):
    """A named bundle of factor weights / strategy config.

    Exactly one row per `symbol` may have `is_active=True` at any time.
    The Backtest Lab's "Promote" action flips the active row.
    """

    __tablename__ = "bt_factor_weight_sets"

    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    symbol = Column(String(32), nullable=False, index=True)
    model_version = Column(String(64), nullable=False, default="v1.0")
    weights = Column(JSON, nullable=False)            # {factor_name: weight}
    strategy_cfg = Column(JSON, nullable=True)        # arbitrary strategy knobs
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=False, index=True)
    created_from_run_id = Column(Integer, ForeignKey("bt_runs.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    activated_at = Column(DateTime, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "symbol": self.symbol,
            "model_version": self.model_version,
            "weights": self.weights,
            "strategy_cfg": self.strategy_cfg,
            "description": self.description,
            "is_active": self.is_active,
            "created_from_run_id": self.created_from_run_id,
            "created_at": _iso(self.created_at),
            "activated_at": _iso(self.activated_at),
        }


class BacktestRun(Base):
    __tablename__ = "bt_runs"

    id = Column(Integer, primary_key=True)
    name = Column(String(160), nullable=True)
    symbol = Column(String(32), nullable=False, index=True)
    interval = Column(String(8), nullable=False, default="1d")  # 1h / 4h / 1d
    start_ts = Column(DateTime, nullable=False, index=True)
    end_ts = Column(DateTime, nullable=False, index=True)

    model_version = Column(String(64), nullable=False, default="v1.0")
    model_kind = Column(String(64), nullable=False, default="weighted")
    horizon = Column(String(8), nullable=False, default="1d")
    ablation_mode = Column(String(64), nullable=True)
    oasis_simulation_id = Column(String(64), nullable=True)
    factor_weights = Column(JSON, nullable=False)     # snapshot of weights used
    strategy_cfg = Column(JSON, nullable=True)
    sentiment_sources = Column(JSON, nullable=True)   # ["fmp","binance_d1"]

    status = Column(String(16), nullable=False, default="pending", index=True)
    # pending / running / completed / failed
    progress = Column(Float, nullable=False, default=0.0)  # 0..1
    error = Column(Text, nullable=True)

    metrics = Column(JSON, nullable=True)             # brier, ic, hit_rate, sharpe...
    equity_curve = Column(JSON, nullable=True)        # [{ts, equity, benchmark}]
    trade_log = Column(JSON, nullable=True)           # executed trades / open marks
    execution_config = Column(JSON, nullable=True)    # markettime-style execution knobs
    factor_evidence = Column(JSON, nullable=True)     # IC/regression/group diagnostics
    backtest_conclusion = Column(JSON, nullable=True) # UI-ready summary and warnings
    factor_importance = Column(JSON, nullable=True)   # {factor: contribution}
    ablation_results = Column(JSON, nullable=True)
    model_debug = Column(JSON, nullable=True)
    feature_schema = Column(JSON, nullable=True)

    created_at = Column(DateTime, nullable=False, default=_utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    predictions = relationship(
        "BacktestPrediction", back_populates="run",
        cascade="all, delete-orphan", lazy="dynamic",
    )

    def to_dict(self, include_curves: bool = True) -> Dict[str, Any]:
        out = {
            "id": self.id,
            "name": self.name,
            "symbol": self.symbol,
            "interval": self.interval,
            "start_ts": _iso(self.start_ts),
            "end_ts": _iso(self.end_ts),
            "model_version": self.model_version,
            "model_kind": self.model_kind,
            "horizon": self.horizon,
            "ablation_mode": self.ablation_mode,
            "oasis_simulation_id": self.oasis_simulation_id,
            "factor_weights": self.factor_weights,
            "strategy_cfg": self.strategy_cfg,
            "sentiment_sources": self.sentiment_sources,
            "status": self.status,
            "progress": self.progress,
            "error": self.error,
            "metrics": self.metrics,
            "created_at": _iso(self.created_at),
            "started_at": _iso(self.started_at),
            "completed_at": _iso(self.completed_at),
        }
        if include_curves:
            out["equity_curve"] = self.equity_curve
            out["trade_log"] = self.trade_log
            out["execution_config"] = self.execution_config
            out["factor_evidence"] = self.factor_evidence
            out["backtest_conclusion"] = self.backtest_conclusion
            out["factor_importance"] = self.factor_importance
            out["ablation_results"] = self.ablation_results
            out["model_debug"] = self.model_debug
            out["feature_schema"] = self.feature_schema
        return out


class BacktestPrediction(Base):
    __tablename__ = "bt_predictions"

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("bt_runs.id"), nullable=False, index=True)
    ts = Column(DateTime, nullable=False, index=True)         # forecast anchor
    horizon = Column(String(8), nullable=False, default="1d")  # 1d / 1w

    predicted_prob_up = Column(Float, nullable=True)
    predicted_prob_down = Column(Float, nullable=True)
    predicted_price = Column(Float, nullable=True)
    predicted_band_low = Column(Float, nullable=True)
    predicted_band_high = Column(Float, nullable=True)
    predicted_distribution = Column(JSON, nullable=True)      # [{bin_low,bin_high,prob}]

    realized_close = Column(Float, nullable=True)
    realized_return = Column(Float, nullable=True)
    hit = Column(Boolean, nullable=True)
    pnl = Column(Float, nullable=True)
    sentiment_snapshot = Column(JSON, nullable=True)          # debug payload
    feature_vector = Column(JSON, nullable=True)
    feature_contribution = Column(JSON, nullable=True)
    model_score = Column(Float, nullable=True)

    run = relationship("BacktestRun", back_populates="predictions")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "ts": _iso(self.ts),
            "horizon": self.horizon,
            "predicted_prob_up": self.predicted_prob_up,
            "predicted_prob_down": self.predicted_prob_down,
            "p_up_1d": self.predicted_prob_up if self.horizon == "1d" else None,
            "p_up_7d": self.predicted_prob_up if self.horizon in {"7d", "1w"} else None,
            "predicted_price": self.predicted_price,
            "predicted_band_low": self.predicted_band_low,
            "predicted_band_high": self.predicted_band_high,
            "predicted_distribution": self.predicted_distribution,
            "realized_close": self.realized_close,
            "realized_return": self.realized_return,
            "hit": self.hit,
            "pnl": self.pnl,
            "confidence": abs((self.predicted_prob_up or 0.5) - 0.5) * 2.0 if self.predicted_prob_up is not None else None,
            "execution": (self.sentiment_snapshot or {}).get("execution") if isinstance(self.sentiment_snapshot, dict) else None,
            "sentiment_snapshot": self.sentiment_snapshot,
            "feature_vector": self.feature_vector,
            "feature_contribution": self.feature_contribution,
            "model_score": self.model_score,
        }


def ensure_backtest_schema() -> None:
    """Best-effort SQLite migration for local lab tables."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    if engine.dialect.name != "sqlite":
        return
    additions = {
        "bt_runs": {
            "model_kind": "VARCHAR(64) DEFAULT 'weighted' NOT NULL",
            "horizon": "VARCHAR(8) DEFAULT '1d' NOT NULL",
            "ablation_mode": "VARCHAR(64)",
            "oasis_simulation_id": "VARCHAR(64)",
            "ablation_results": "JSON",
            "model_debug": "JSON",
            "feature_schema": "JSON",
            "trade_log": "JSON",
            "execution_config": "JSON",
            "factor_evidence": "JSON",
            "backtest_conclusion": "JSON",
        },
        "bt_predictions": {
            "feature_vector": "JSON",
            "feature_contribution": "JSON",
            "model_score": "FLOAT",
        },
    }
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table, cols in additions.items():
            if table not in inspector.get_table_names():
                continue
            existing = {col["name"] for col in inspector.get_columns(table)}
            for name, ddl in cols.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


ensure_backtest_schema()
