"""Polymarket read-only integration package.

This package only consumes public Polymarket REST endpoints
(`gamma-api.polymarket.com` and `clob.polymarket.com`). It deliberately does
NOT import `py-clob-client`, `web3`, or any signing libraries — the FinRex
deployment never holds USDC, never signs orders, and only uses the data for
internal weekly validation.
"""

from .client import PolymarketClient  # noqa: F401
from .orderbook import BookLevel, OrderBook  # noqa: F401
