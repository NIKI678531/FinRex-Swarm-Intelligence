"""Paper-trading portfolio tests with a mocked quote function."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_paper_trading_buy_sell_flow(monkeypatch, tmp_path):
    from app.quant import config
    from app.quant.paper_trading import portfolio

    # Redirect persistence
    monkeypatch.setattr(config, "PAPER_TRADING_DIR", tmp_path)

    # Mutable price for quote
    state = {"price": 100.0}
    monkeypatch.setattr(portfolio, "latest_quote", lambda symbol: state["price"])

    acc = portfolio.create_account("Test", initial_cash=10000.0, ccy="USD")
    assert acc["cash"] == 10000.0
    assert acc["positions"] == {}

    # Buy 10 BTC at 100 → spent ~1000 + fee
    order = portfolio.place_order(
        acc["account_id"], "BTC-USDT", "buy", qty=10.0, order_type="market",
    )
    assert order["status"] == "filled"
    assert order["side"] == "buy"

    snap = portfolio.snapshot(acc["account_id"])
    assert len(snap["positions"]) == 1
    pos = snap["positions"][0]
    assert pos["symbol"] == "BTC-USDT"
    assert abs(pos["qty"] - 10.0) < 1e-9
    assert snap["total_equity"] > 9000.0  # rough sanity

    # Price moves up → unrealized PnL > 0
    state["price"] = 120.0
    snap2 = portfolio.snapshot(acc["account_id"])
    assert snap2["positions"][0]["unrealized_pnl"] > 0

    # Sell entire position
    portfolio.place_order(
        acc["account_id"], "BTC-USDT", "sell", qty=10.0, order_type="market",
    )
    snap3 = portfolio.snapshot(acc["account_id"])
    assert snap3["positions"] == []
    assert snap3["cumulative_return"] > 0  # profit captured


def test_paper_trading_insufficient_cash_raises(monkeypatch, tmp_path):
    from app.quant import config
    from app.quant.paper_trading import portfolio

    monkeypatch.setattr(config, "PAPER_TRADING_DIR", tmp_path)
    monkeypatch.setattr(portfolio, "latest_quote", lambda symbol: 1000.0)

    acc = portfolio.create_account("Tiny", initial_cash=500.0)
    try:
        portfolio.place_order(acc["account_id"], "BTC-USDT", "buy",
                              qty=10.0, order_type="market")
    except ValueError as e:
        assert "cash" in str(e).lower()
    else:
        raise AssertionError("expected ValueError")


def test_paper_trading_unknown_symbol_raises(monkeypatch, tmp_path):
    from app.quant import config
    from app.quant.paper_trading import portfolio

    monkeypatch.setattr(config, "PAPER_TRADING_DIR", tmp_path)
    monkeypatch.setattr(portfolio, "latest_quote", lambda symbol: 1.0)

    acc = portfolio.create_account("X", initial_cash=1000.0)
    try:
        portfolio.place_order(acc["account_id"], "NOPE-XXX", "buy",
                              qty=1.0, order_type="market")
    except ValueError as e:
        assert "unknown" in str(e).lower() or "symbol" in str(e).lower()
    else:
        raise AssertionError("expected ValueError")


def test_list_accounts_returns_created(monkeypatch, tmp_path):
    from app.quant import config
    from app.quant.paper_trading import portfolio

    monkeypatch.setattr(config, "PAPER_TRADING_DIR", tmp_path)
    monkeypatch.setattr(portfolio, "latest_quote", lambda symbol: 1.0)

    a1 = portfolio.create_account("A1", initial_cash=1000.0)
    a2 = portfolio.create_account("A2", initial_cash=2000.0)
    ids = {a["account_id"] for a in portfolio.list_accounts()}
    assert a1["account_id"] in ids and a2["account_id"] in ids
