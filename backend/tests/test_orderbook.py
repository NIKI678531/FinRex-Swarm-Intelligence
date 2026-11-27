"""Tests for the OrderBook VWAP / market-impact / slippage primitives."""

from datetime import datetime, timezone

import pytest

from app.services.polymarket.orderbook import BookLevel, OrderBook


def _book(asks, bids=None, token="tok-1"):
    """Build an OrderBook from raw [(price, size), ...] tuples."""
    return OrderBook(
        token_id=token,
        asks=[BookLevel(p, s) for p, s in asks],
        bids=[BookLevel(p, s) for p, s in (bids or [])],
        timestamp=datetime.now(timezone.utc),
    )


class TestFromClob:
    def test_parses_and_sorts(self):
        payload = {
            "asks": [
                {"price": "0.60", "size": "100"},
                {"price": "0.55", "size": "50"},
                {"price": "0.65", "size": "200"},
            ],
            "bids": [
                {"price": "0.50", "size": "80"},
                {"price": "0.52", "size": "40"},
            ],
            "timestamp": "1715414400",  # epoch s
        }
        ob = OrderBook.from_clob("tok-1", payload)
        assert [l.price for l in ob.asks] == [0.55, 0.60, 0.65]
        assert [l.price for l in ob.bids] == [0.52, 0.50]
        assert ob.best_ask == 0.55
        assert ob.best_bid == 0.52
        assert ob.midpoint == pytest.approx(0.535)

    def test_skips_invalid_levels(self):
        payload = {
            "asks": [
                {"price": "0.55", "size": "50"},
                {"price": "0", "size": "100"},      # invalid
                {"price": "0.60", "size": "0"},     # invalid
            ],
            "bids": [],
        }
        ob = OrderBook.from_clob("t", payload)
        assert len(ob.asks) == 1
        assert ob.asks[0].price == 0.55


class TestVwapBuy:
    def test_single_level_full_fill(self):
        ob = _book([(0.50, 200)])
        vwap, shares, unfilled = ob.vwap_buy(50)
        assert vwap == pytest.approx(0.50)
        assert shares == pytest.approx(100)
        assert unfilled == 0

    def test_walks_multiple_levels(self):
        # $100 at 0.50 = 50 shares, then need $50 more → 0.60 buys ~83.33 shares
        ob = _book([(0.50, 100), (0.60, 200)])
        vwap, shares, unfilled = ob.vwap_buy(150)
        # spent $50 at 0.50 (100 shares) + $100 at 0.60 (166.67 shares)
        assert shares == pytest.approx(100 + 100 / 0.60)
        assert vwap == pytest.approx(150 / shares)
        assert unfilled == 0

    def test_partial_fill_when_insufficient_liquidity(self):
        ob = _book([(0.50, 100)])  # max notional = $50
        vwap, shares, unfilled = ob.vwap_buy(200)
        assert shares == pytest.approx(100)
        assert unfilled == pytest.approx(150)
        assert vwap == pytest.approx(0.50)

    def test_zero_or_negative_usd_returns_empty(self):
        ob = _book([(0.50, 100)])
        assert ob.vwap_buy(0) == (None, 0.0, 0.0)
        assert ob.vwap_buy(-10) == (None, 0.0, 0.0)

    def test_empty_book(self):
        ob = _book([])
        vwap, shares, unfilled = ob.vwap_buy(100)
        assert vwap is None
        assert shares == 0
        assert unfilled == 100


class TestVwapBuyMonotonicity:
    def test_vwap_non_decreasing_with_size(self):
        ob = _book([(0.50, 100), (0.55, 100), (0.60, 100), (0.70, 100)])
        last = 0.0
        for usd in (10, 25, 50, 75, 100, 150, 200):
            vwap, _, _ = ob.vwap_buy(usd)
            assert vwap is not None
            assert vwap >= last - 1e-9, f"VWAP regressed at usd={usd}: {vwap} < {last}"
            last = vwap


class TestVwapSell:
    def test_walks_bid_levels(self):
        ob = _book([], bids=[(0.55, 100), (0.50, 200), (0.45, 300)])
        vwap, usd, unfilled = ob.vwap_sell(150)
        # 100 @ 0.55 = $55 + 50 @ 0.50 = $25 → $80 / 150 shares
        assert usd == pytest.approx(80)
        assert vwap == pytest.approx(80 / 150)
        assert unfilled == 0

    def test_partial_sell(self):
        ob = _book([], bids=[(0.50, 50)])
        vwap, usd, unfilled = ob.vwap_sell(200)
        assert usd == pytest.approx(25)
        assert unfilled == 150


class TestSlippageAndImpactCurve:
    def test_slippage_zero_for_top_of_book_only(self):
        ob = _book([(0.50, 1000)])
        slip = ob.slippage_pct(10)
        assert slip == pytest.approx(0.0)

    def test_slippage_positive_when_walking_book(self):
        ob = _book([(0.50, 100), (0.70, 100)])
        slip = ob.slippage_pct(150)  # forces walk into 0.70 level
        assert slip is not None
        assert slip > 0

    def test_market_impact_curve_shape(self):
        ob = _book([(0.50, 100), (0.55, 100), (0.60, 100)])
        curve = ob.market_impact_curve(usd_max=150, steps=5)
        assert len(curve) == 5
        # vwap should be non-decreasing
        vwaps = [pt["vwap"] for pt in curve]
        assert vwaps == sorted(vwaps)
        # payout multiple = 1 / vwap
        for pt in curve:
            assert pt["payout_multiple"] == pytest.approx(1.0 / pt["vwap"], rel=1e-3)


class TestMaxSizeWithinSlippage:
    def test_returns_zero_for_empty_book(self):
        ob = _book([])
        assert ob.max_size_within_slippage(midpoint=0.5) == 0.0

    def test_full_book_within_cap(self):
        # Single deep level → all of it fills at one price = 0% slippage
        ob = _book([(0.50, 1000)])
        result = ob.max_size_within_slippage(midpoint=0.50, max_slippage_pct=0.02)
        assert result == pytest.approx(500.0)

    def test_finds_size_under_cap(self):
        # First $50 fills at 0.50 (0% slip), beyond that fills at 0.60 (20% slip)
        ob = _book([(0.50, 100), (0.60, 1000)])
        result = ob.max_size_within_slippage(midpoint=0.50, max_slippage_pct=0.02)
        # Should be close to $50 (the full first level) — 2% of 0.50 = 0.51 cap
        assert 40 <= result <= 65


class TestNotionalStats:
    def test_total_notionals(self):
        ob = _book([(0.50, 100), (0.60, 50)], bids=[(0.45, 200)])
        assert ob.total_ask_notional() == pytest.approx(50 + 30)
        assert ob.total_bid_notional() == pytest.approx(90)
