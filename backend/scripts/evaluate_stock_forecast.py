#!/usr/bin/env python3
"""Phase F — Per-factor T+1 hit-rate backtest for StockForecastService.

For each symbol and each historical day we compute the 6 factor scores using
data available *as of that day*, then compare each factor's sign against the
actual T+1 return. Outputs a CSV-style summary per factor and overall composite.

Usage:
    python scripts/evaluate_stock_forecast.py --symbols NVDA,TSLA,AAPL --days 30

Notes:
- Uses real MarketProvider (yfinance fallback for OHLCV); sentiment / news
  set to dummy providers so the backtest is reproducible and offline-friendly.
- For full sentiment-aware backtest, swap DummySentimentProvider with the real
  SentimentProvider (will hit LLM/HF).
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.services.financial.market_provider import MarketProvider  # noqa: E402
from app.services.financial.stock_forecast_service import (  # noqa: E402
    StockForecastService,
    _STOCK_WEIGHTS,
    _DIRECTION_THRESHOLD,
)


class _DummyNews:
    @staticmethod
    def collect_corpus(symbol, asset_type="stock", user_comments=None, selected_articles=None,
                       news_limit=20, hours=72, include_press_releases=True,
                       include_general_news=True, general_news_query=None):
        return {"ok": True, "all": [], "news": [], "user_comments": [], "selected_articles": [],
                "press_releases": [], "general_news": []}


class _DummySentiment:
    @staticmethod
    def score_corpus(items):
        return {
            "ok": False, "model": "dummy", "count": 0, "average_compound": 0.0,
            "weighted_avg_compound": 0.0,
            "summary": {"count": 0, "average_compound": 0.0, "weighted_avg_compound": 0.0,
                        "pos_ratio": 0.0, "neg_ratio": 0.0, "neu_ratio": 1.0},
            "timeline": [], "items": [],
        }


def _slice_market_provider(real: MarketProvider, as_of_idx: int, full_rows: List[Dict[str, Any]]):
    """Return a market-provider-like object that exposes data up to as_of_idx (inclusive)."""

    class Sliced:
        def fetch_snapshot(self, symbol, asset_type="stock", lookback_days=180, min_rows=0):
            sub = full_rows[max(0, as_of_idx - lookback_days + 1): as_of_idx + 1]
            if not sub:
                return {"ok": False, "symbol": symbol, "normalized_symbol": symbol,
                        "asset_type": asset_type, "rows_count": 0, "ohlcv": [],
                        "indicators": {}, "source": "sliced", "fetched_at": None}
            closes = [r["close"] for r in sub]
            last = closes[-1]
            ma20 = sum(closes[-20:]) / 20.0 if len(closes) >= 20 else last
            ma60 = sum(closes[-60:]) / 60.0 if len(closes) >= 60 else last
            trend = "up" if last > ma20 > ma60 else ("down" if last < ma20 < ma60 else "sideways")
            return {
                "ok": True, "symbol": symbol, "normalized_symbol": symbol,
                "asset_type": asset_type, "rows_count": len(sub), "ohlcv": sub,
                "indicators": {
                    "last_close": last, "ma20": ma20, "ma60": ma60,
                    "rsi14": None,
                    "return_5d": (closes[-1] / closes[-6] - 1.0) if len(closes) > 6 else 0.0,
                    "return_30d": (closes[-1] / closes[-31] - 1.0) if len(closes) > 31 else 0.0,
                    "volatility_30d": 0.02, "trend": trend,
                },
                "source": "sliced", "fetched_at": sub[-1].get("date"),
            }

        def fetch_overnight_gap(self, symbol):
            if as_of_idx >= 1:
                prev = full_rows[as_of_idx - 1]["close"]
                cur_open = full_rows[as_of_idx].get("open", full_rows[as_of_idx]["close"])
                gap = (cur_open - prev) / prev if prev else 0.0
                import math
                return {"ok": True, "symbol": symbol, "gap_pct": gap,
                        "factor": math.tanh(gap / 0.03), "source": "sliced"}
            return {"ok": False, "reason": "insufficient history"}

        def fetch_benchmark_trend(self, symbol, lookback_days=30):
            sub = full_rows[max(0, as_of_idx - lookback_days + 1): as_of_idx + 1]
            if len(sub) < 2:
                return {"ok": False, "reason": "insufficient history"}
            ret = sub[-1]["close"] / sub[0]["close"] - 1.0
            return {"ok": True, "symbol": symbol, "benchmark": "self",
                    "benchmark_return_30d": ret, "beta": 1.0,
                    "factor": max(-1.0, min(1.0, ret * 8.0)), "source": "sliced"}

        def fetch_options_signal(self, symbol):
            return {"ok": False, "reason": "options PCR unavailable"}

        def fetch_earnings_window(self, symbol, window_days=5):
            return {"ok": True, "symbol": symbol, "in_window": False,
                    "days_to_event": None, "event_date": None, "source": "sliced"}

    return Sliced()


def evaluate_symbol(symbol: str, days: int) -> Dict[str, Any]:
    real = MarketProvider()
    snapshot = real.fetch_snapshot(symbol, asset_type="stock", lookback_days=max(180, days + 90))
    rows = snapshot.get("ohlcv") or []
    if len(rows) < days + 60:
        return {"symbol": symbol, "ok": False, "reason": f"insufficient history ({len(rows)} rows)"}

    factor_keys = [
        "sentiment",
        "technical",
        "technical_multi",
        "technical_llm",
        "market_beta",
        "overnight_gap",
        "options_iv",
        "oasis_pulse",
        "composite",
    ]
    factor_hits: Dict[str, int] = {k: 0 for k in factor_keys}
    factor_total: Dict[str, int] = {k: 0 for k in factor_hits}

    start_idx = len(rows) - days - 1  # need T+1 for last sample
    for i in range(start_idx, len(rows) - 1):
        if i < 60:
            continue
        sliced = _slice_market_provider(real, i, rows)
        svc = StockForecastService(market_provider=sliced,
                                   sentiment_provider=_DummySentiment(),
                                   news_provider=_DummyNews())
        out = svc.forecast(symbol=symbol, comments=[], articles=[])
        fb = out.get("score_breakdown", {})
        next_ret = rows[i + 1]["close"] / rows[i]["close"] - 1.0
        actual_dir = 1 if next_ret > 0 else (-1 if next_ret < 0 else 0)
        for k in [
            "sentiment",
            "technical",
            "technical_multi",
            "technical_llm",
            "market_beta",
            "overnight_gap",
            "options_iv",
            "oasis_pulse",
        ]:
            v = fb.get(k, 0.0)
            if abs(v) < 1e-6:
                continue
            pred = 1 if v > 0 else -1
            factor_total[k] += 1
            if pred == actual_dir:
                factor_hits[k] += 1
        comp = fb.get("composite", 0.0)
        if abs(comp) >= _DIRECTION_THRESHOLD:
            pred = 1 if comp > 0 else -1
            factor_total["composite"] += 1
            if pred == actual_dir:
                factor_hits["composite"] += 1

    rates = {k: (factor_hits[k] / factor_total[k]) if factor_total[k] else None for k in factor_hits}
    return {
        "symbol": symbol,
        "ok": True,
        "samples": days,
        "weights": _STOCK_WEIGHTS,
        "hit_rates": rates,
        "counts": factor_total,
    }


def main():
    parser = argparse.ArgumentParser(description="Per-factor T+1 backtest for stock forecast")
    parser.add_argument("--symbols", default="NVDA,TSLA,AAPL,MSFT,SPY", help="Comma-separated tickers")
    parser.add_argument("--days", type=int, default=30, help="Backtest horizon (most recent N days)")
    parser.add_argument("--out", default=None, help="Optional CSV output path")
    parser.add_argument("--with-llm", action="store_true", help="Allow real STOCK_TECH_LLM calls during evaluation")
    args = parser.parse_args()
    if not args.with_llm:
        os.environ["STOCK_TECH_LLM_ENABLED"] = "false"

    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    results = [evaluate_symbol(s, args.days) for s in syms]

    print(
        f"\n{'symbol':<8} {'sent':>8} {'tech':>8} {'multi':>8} {'llm':>8} "
        f"{'beta':>8} {'gap':>8} {'opt':>8} {'pulse':>8} {'comp':>8}"
    )
    for r in results:
        if not r.get("ok"):
            print(f"{r['symbol']:<8}  -- {r.get('reason')}")
            continue
        h = r["hit_rates"]
        def fmt(k):
            v = h.get(k)
            return f"{v:.3f}" if v is not None else "  n/a"
        print(
            f"{r['symbol']:<8} {fmt('sentiment'):>8} {fmt('technical'):>8} "
            f"{fmt('technical_multi'):>8} {fmt('technical_llm'):>8} "
            f"{fmt('market_beta'):>8} {fmt('overnight_gap'):>8} "
            f"{fmt('options_iv'):>8} {fmt('oasis_pulse'):>8} {fmt('composite'):>8}"
        )

    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                "symbol", "samples", "sentiment", "technical", "technical_multi",
                "technical_llm", "market_beta", "overnight_gap", "options_iv",
                "oasis_pulse", "composite",
            ])
            for r in results:
                if r.get("ok"):
                    h = r["hit_rates"]
                    w.writerow([r["symbol"], r["samples"], h.get("sentiment"), h.get("technical"),
                                h.get("technical_multi"), h.get("technical_llm"),
                                h.get("market_beta"), h.get("overnight_gap"),
                                h.get("options_iv"), h.get("oasis_pulse"),
                                h.get("composite")])
        print(f"\nCSV written to: {args.out}")


if __name__ == "__main__":
    main()
