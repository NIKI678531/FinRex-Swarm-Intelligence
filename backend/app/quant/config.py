"""Quant subsystem configuration (paths, default windows, supported symbols)."""

from __future__ import annotations

import os
from pathlib import Path

# Allow env override; otherwise sit alongside existing backend/uploads/
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
QUANT_DATA_ROOT = Path(os.environ.get(
    "QUANT_DATA_ROOT",
    _BACKEND_ROOT / "uploads" / "quant",
))

MARKET_CACHE_DIR = QUANT_DATA_ROOT / "market_cache"
NEWS_CACHE_DIR = QUANT_DATA_ROOT / "news_cache"
QLIB_DATA_DIR = QUANT_DATA_ROOT / "qlib_data"
BACKTEST_RUNS_DIR = QUANT_DATA_ROOT / "backtest_runs"
PAPER_TRADING_DIR = QUANT_DATA_ROOT / "paper_trading"
OASIS_BACKFILL_DIR = QUANT_DATA_ROOT / "oasis_backfill"
PRICE_CALIBRATION_DIR = QUANT_DATA_ROOT / "price_calibration"

# Walk-forward defaults (calendar days)
WF_TRAIN_DAYS = int(os.environ.get("QUANT_WF_TRAIN_DAYS", "480"))
WF_TEST_DAYS = int(os.environ.get("QUANT_WF_TEST_DAYS", "120"))
WF_STEP_DAYS = int(os.environ.get("QUANT_WF_STEP_DAYS", "30"))

# Prediction horizon (T+N return direction). Default 1 = next-day prediction.
PREDICT_HORIZON_DAYS = int(os.environ.get("QUANT_PREDICT_HORIZON", "1"))

# Interactive price-point backtests must not run hundreds of foundation-model
# inferences. By default the historical walk-forward raw model is the fast
# volatility/quantile model; set mode to tail/sample/full for offline foundation
# calibration experiments.
PRICE_ML_FOUNDATION_MODE = os.environ.get("QUANT_PRICE_ML_FOUNDATION_MODE", "none").lower()
PRICE_ML_MAX_FOUNDATION_CALLS = int(os.environ.get("QUANT_PRICE_ML_MAX_FOUNDATION_CALLS", "1"))
PRICE_ML_MAX_BACKTEST_BARS = int(os.environ.get("QUANT_PRICE_ML_MAX_BACKTEST_BARS", "360"))
PRICE_ML_RETRAIN_EVERY = int(os.environ.get("QUANT_PRICE_ML_RETRAIN_EVERY", "60"))

# Swarm factor rolling z-score window
SWARM_ZSCORE_WINDOW = int(os.environ.get("QUANT_SWARM_ZSCORE_WINDOW", "60"))
SWARM_FFILL_LIMIT = int(os.environ.get("QUANT_SWARM_FFILL_LIMIT", "3"))

# Foundation forecasting models (Phase 3)
# Kronos: NeoQuasar/Kronos-small — domain-specific OHLCV foundation model (AAAI 2026)
# Chronos-Bolt: amazon/chronos-bolt-small — general-purpose probabilistic time-series model
KRONOS_ENABLED = os.environ.get("QUANT_KRONOS_ENABLED", "true").lower() in ("1", "true", "yes")
KRONOS_MODEL_ID = os.environ.get("QUANT_KRONOS_MODEL_ID", "NeoQuasar/Kronos-small")
KRONOS_TOKENIZER_ID = os.environ.get("QUANT_KRONOS_TOKENIZER_ID", "NeoQuasar/Kronos-Tokenizer-base")
KRONOS_NUM_SAMPLES = int(os.environ.get("QUANT_KRONOS_NUM_SAMPLES", "16"))
KRONOS_CONTEXT_LEN = int(os.environ.get("QUANT_KRONOS_CONTEXT_LEN", "256"))

CHRONOS_ENABLED = os.environ.get("QUANT_CHRONOS_ENABLED", "true").lower() in ("1", "true", "yes")
CHRONOS_MODEL_ID = os.environ.get("QUANT_CHRONOS_MODEL_ID", "amazon/chronos-bolt-small")
CHRONOS_CONTEXT_LEN = int(os.environ.get("QUANT_CHRONOS_CONTEXT_LEN", "512"))

# kronos+chronos | kronos_only | chronos_only | none
FOUNDATION_ENSEMBLE = os.environ.get("QUANT_FOUNDATION_ENSEMBLE", "kronos+chronos")

# ---------------------------------------------------------------------------
# Auto paper-trading (signal-driven automatic order placement for system A)
# ---------------------------------------------------------------------------
# Comma-separated canonical symbols the auto-trader will scan each cycle.
AUTO_TRADE_WATCHLIST = [
    s.strip()
    for s in os.environ.get(
        "QUANT_AUTO_TRADE_WATCHLIST",
        "BTC-USDT,ETH-USDT,AAPL,3033.HK",
    ).split(",")
    if s.strip()
]

# Fused directional score must exceed this magnitude to trigger a trade.
AUTO_TRADE_SCORE_THRESHOLD = float(os.environ.get("QUANT_AUTO_TRADE_SCORE_THRESHOLD", "0.15"))
# Fused confidence must be at least this to trade.
AUTO_TRADE_MIN_CONFIDENCE = float(os.environ.get("QUANT_AUTO_TRADE_MIN_CONFIDENCE", "0.25"))
# Max fraction of total equity to deploy in a single auto order (before confidence scaling).
AUTO_TRADE_MAX_POSITION_PCT = float(os.environ.get("QUANT_AUTO_TRADE_MAX_POSITION_PCT", "0.05"))
# Keep at least this fraction of equity in cash (do not fully invest).
AUTO_TRADE_CASH_RESERVE_PCT = float(os.environ.get("QUANT_AUTO_TRADE_CASH_RESERVE_PCT", "0.10"))
# Cooldown (minutes) before the same symbol+direction may be auto-traded again.
AUTO_TRADE_COOLDOWN_MINUTES = int(os.environ.get("QUANT_AUTO_TRADE_COOLDOWN_MINUTES", "360"))
# When True, a sell signal on a held position is allowed to flatten/reduce it.
AUTO_TRADE_ALLOW_SELL = os.environ.get("QUANT_AUTO_TRADE_ALLOW_SELL", "true").lower() in ("1", "true", "yes")
# Dedicated account the scheduler operates on (isolated from manual accounts).
AUTO_TRADE_ACCOUNT_ID = os.environ.get("QUANT_AUTO_TRADE_ACCOUNT_ID", "").strip() or None
AUTO_TRADE_ACCOUNT_NAME = os.environ.get("QUANT_AUTO_TRADE_ACCOUNT_NAME", "Auto Trader")
AUTO_TRADE_INITIAL_CASH = float(os.environ.get("QUANT_AUTO_TRADE_INITIAL_CASH", "100000"))


def ensure_dirs() -> None:
    for d in (
        QUANT_DATA_ROOT,
        MARKET_CACHE_DIR,
        NEWS_CACHE_DIR,
        QLIB_DATA_DIR,
        BACKTEST_RUNS_DIR,
        PAPER_TRADING_DIR,
        OASIS_BACKFILL_DIR,
        PRICE_CALIBRATION_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)
