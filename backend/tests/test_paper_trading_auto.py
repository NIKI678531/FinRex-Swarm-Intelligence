"""Unit tests for the auto paper-trader: pending-order matching, signal
fusion, and signal-driven order placement."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.quant import config
from app.quant.paper_trading import auto_trader, portfolio, signal_fusion


@pytest.fixture()
def tmp_accounts(tmp_path, monkeypatch):
    """Isolate paper-trading account storage to a temp dir."""
    monkeypatch.setattr(config, "PAPER_TRADING_DIR", tmp_path)
    monkeypatch.setattr(portfolio.config, "PAPER_TRADING_DIR", tmp_path)
    return tmp_path


def _patch_quote(monkeypatch, price):
    monkeypatch.setattr(portfolio, "latest_quote", lambda symbol: float(price))


# ---------------------------------------------------------------------------
# Pending limit-order matching
# ---------------------------------------------------------------------------
def test_pending_limit_order_fills_when_price_crosses(tmp_accounts, monkeypatch):
    _patch_quote(monkeypatch, 100.0)
    acc = portfolio.create_account("t", initial_cash=10_000.0)
    acc_id = acc["account_id"]

    # Buy limit below market → parked as pending (no fill yet).
    order = portfolio.place_order(acc_id, "AAPL", "buy", qty=10, order_type="limit", limit_price=90.0)
    assert order["status"] == "pending"
    assert portfolio.match_pending_orders(acc_id) == []

    # Price dips to/below the limit → order fills on the next pass.
    _patch_quote(monkeypatch, 85.0)
    filled = portfolio.match_pending_orders(acc_id)
    assert len(filled) == 1
    assert filled[0]["status"] == "filled"

    snap = portfolio.snapshot(acc_id)
    held = next(p for p in snap["positions"] if p["symbol"] == "AAPL")
    assert held["qty"] == pytest.approx(10)
    # Cash reduced by 10 * 90 (limit price), not the 85 market price.
    assert snap["cash"] == pytest.approx(10_000.0 - 900.0)


def test_market_order_records_meta(tmp_accounts, monkeypatch):
    _patch_quote(monkeypatch, 50.0)
    acc = portfolio.create_account("t", initial_cash=10_000.0)
    acc_id = acc["account_id"]

    order = portfolio.place_order(
        acc_id, "AAPL", "buy", qty=5, order_type="market",
        meta={"source": "auto_trader", "fingerprint": "AAPL:up:x"},
    )
    assert order["status"] == "filled"
    assert order["meta"]["source"] == "auto_trader"

    doc = portfolio.get_account(acc_id)
    assert len(doc["equity_curve"]) >= 2  # creation point + post-trade mtm


# ---------------------------------------------------------------------------
# Signal fusion
# ---------------------------------------------------------------------------
def test_fuse_agreeing_sources_are_bullish(monkeypatch):
    sources = [
        {"name": "quant_pipeline", "score": 0.6, "confidence": 0.7, "raw": {}},
        {"name": "stock_forecast", "score": 0.4, "confidence": 0.5, "raw": {}},
    ]
    monkeypatch.setattr(signal_fusion, "collect_sources", lambda s: sources)
    out = signal_fusion.fuse("AAPL")
    assert out["ok"] is True
    assert out["direction"] == "up"
    assert out["fused_score"] > 0
    assert out["agreement"] == pytest.approx(1.0)
    assert out["fused_confidence"] > 0


def test_fuse_conflicting_sources_attenuate(monkeypatch):
    sources = [
        {"name": "a", "score": 0.8, "confidence": 0.6, "raw": {}},
        {"name": "b", "score": -0.8, "confidence": 0.6, "raw": {}},
    ]
    monkeypatch.setattr(signal_fusion, "collect_sources", lambda s: sources)
    out = signal_fusion.fuse("AAPL")
    assert abs(out["fused_score"]) < 0.1
    assert out["direction"] == "neutral"
    assert out["fused_confidence"] == pytest.approx(0.0)


def test_fuse_no_sources(monkeypatch):
    monkeypatch.setattr(signal_fusion, "collect_sources", lambda s: [])
    out = signal_fusion.fuse("AAPL")
    assert out["ok"] is False
    assert out["direction"] == "neutral"


# ---------------------------------------------------------------------------
# Auto-trader decisions
# ---------------------------------------------------------------------------
def _fused(direction="up", score=0.5, confidence=0.8):
    return {
        "symbol": "AAPL", "ok": True, "fused_score": score,
        "fused_confidence": confidence, "direction": direction,
        "agreement": 1.0, "n_sources": 2,
        "sources": [{"name": "quant_pipeline"}, {"name": "stock_forecast"}],
    }


def test_decide_buys_on_strong_bullish_signal(tmp_accounts, monkeypatch):
    _patch_quote(monkeypatch, 100.0)
    monkeypatch.setattr(auto_trader.signal_fusion, "fuse", lambda s: _fused())
    acc = portfolio.create_account("auto", initial_cash=100_000.0)
    acc_id = acc["account_id"]

    decision = auto_trader.decide_and_trade(acc_id, "AAPL")
    assert decision.status == "executed"
    assert decision.side == "buy"
    # target = equity 100k * 0.05 * conf 0.8 = 4000 notional → 40 shares @ 100.
    assert decision.notional == pytest.approx(4_000.0, rel=0.01)


def test_decide_skips_below_threshold(tmp_accounts, monkeypatch):
    _patch_quote(monkeypatch, 100.0)
    monkeypatch.setattr(auto_trader.signal_fusion, "fuse", lambda s: _fused(score=0.05))
    acc = portfolio.create_account("auto", initial_cash=100_000.0)
    decision = auto_trader.decide_and_trade(acc["account_id"], "AAPL")
    assert decision.status == "skipped"
    assert "threshold" in decision.reason


def test_decide_cooldown_blocks_repeat(tmp_accounts, monkeypatch):
    _patch_quote(monkeypatch, 100.0)
    monkeypatch.setattr(auto_trader.signal_fusion, "fuse", lambda s: _fused())
    acc = portfolio.create_account("auto", initial_cash=100_000.0)
    acc_id = acc["account_id"]

    first = auto_trader.decide_and_trade(acc_id, "AAPL")
    assert first.status == "executed"
    second = auto_trader.decide_and_trade(acc_id, "AAPL")
    assert second.status == "skipped"
    assert "cooldown" in second.reason


def test_decide_sell_without_position_skips(tmp_accounts, monkeypatch):
    _patch_quote(monkeypatch, 100.0)
    monkeypatch.setattr(auto_trader.signal_fusion, "fuse", lambda s: _fused(direction="down", score=-0.5))
    acc = portfolio.create_account("auto", initial_cash=100_000.0)
    decision = auto_trader.decide_and_trade(acc["account_id"], "AAPL")
    assert decision.status == "skipped"
    assert "no long position" in decision.reason


def test_run_cycle_returns_summary(tmp_accounts, monkeypatch):
    _patch_quote(monkeypatch, 100.0)
    monkeypatch.setattr(auto_trader.signal_fusion, "fuse", lambda s: _fused())
    acc = portfolio.create_account("auto", initial_cash=100_000.0)
    result = auto_trader.run_cycle(acc["account_id"], watchlist=["AAPL"])
    assert result["executed"] == 1
    assert len(result["decisions"]) == 1
