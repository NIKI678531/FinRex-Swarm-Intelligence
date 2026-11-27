"""CSOP ETF asset forecast & allocation module.

Sidecar module that augments the existing report layer with quantitative
forecasts and asset allocation suggestions for CSOP (南方东英) ETF products.

Public surface:
- ``forecast_service.AssetForecastService.build_for_report(report)`` — main entry
- ``etf_universe.EtfUniverse`` — product master data
- ``signal_engine`` / ``indicators`` / ``risk_metrics`` — computation primitives
- ``market_data.MarketDataService`` — yfinance OHLCV loader with disk cache

Designed to be **non-invasive**: nothing in this package mutates existing
report / strategy / v2 adapter data. It reads from them and produces a
parallel "asset_allocation" bundle that the frontend consumes via the
``/api/report/<id>/asset-allocation`` endpoint.
"""

from .forecast_service import AssetForecastService  # noqa: F401
from .etf_universe import EtfUniverse  # noqa: F401
