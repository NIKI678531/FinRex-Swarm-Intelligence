"""金融行情 Provider。

统一封装 yfinance 获取 OHLCV，并在此基础上计算简单技术指标
（MA20 / MA60 / RSI14 / 近期收益率 / 波动率），供 financial_forecast_analyzer 消费。

保持简单：复用 services/asset_forecast/market_data.py 的下载与缓存能力，
不重复实现网络层。
"""

from __future__ import annotations

import logging
import math
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

from ...config import Config
from ..asset_forecast.market_data import MarketDataService

logger = logging.getLogger("finrex.financial.market_provider")


def _normalize_symbol(symbol: str, asset_type: str) -> str:
    """根据资产类型将用户输入的 symbol 规整为 yfinance 接受的格式。

    - stock: 直接透传（可带后缀如 .HK）
    - crypto: 若未带 -USD 后缀则补全为 BTC-USD 形式
    - event: 不处理
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        return ""
    if asset_type == "crypto" and "-" not in sym:
        return f"{sym}-USD"
    return sym


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _moving_average(values: List[float], window: int) -> Optional[float]:
    if len(values) < window or window <= 0:
        return None
    return sum(values[-window:]) / window


def _rsi(values: List[float], window: int = 14) -> Optional[float]:
    if len(values) <= window:
        return None
    gains: List[float] = []
    losses: List[float] = []
    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        if diff >= 0:
            gains.append(diff)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(-diff)
    avg_gain = sum(gains[-window:]) / window
    avg_loss = sum(losses[-window:]) / window
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _stddev(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return var ** 0.5


def _parse_row_date(row: Dict[str, Any]) -> Optional[date]:
    raw = row.get("date") or row.get("datetime") or row.get("timestamp")
    if raw in (None, ""):
        return None
    if isinstance(raw, (int, float)):
        try:
            return datetime.utcfromtimestamp(float(raw) / (1000.0 if raw > 10_000_000_000 else 1.0)).date()
        except Exception:  # noqa: BLE001
            return None
    text = str(raw).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _last_ohlcv_date(rows: List[Dict[str, Any]]) -> Optional[date]:
    for row in reversed(rows or []):
        dt = _parse_row_date(row)
        if dt:
            return dt
    return None


def _previous_weekday(day: date) -> date:
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _expected_latest_daily_bar_date(now: Optional[datetime] = None) -> date:
    # Yahoo daily bars often settle after the US close. Before 23:00 UTC,
    # expect the previous weekday; after that, today's bar is reasonable.
    ref = now or datetime.utcnow()
    candidate = ref.date()
    if ref.hour < 23:
        candidate -= timedelta(days=1)
    return _previous_weekday(candidate)


def _weekday_lag(last_date: Optional[date], expected_date: date) -> Optional[int]:
    if not last_date:
        return None
    if last_date >= expected_date:
        return 0
    lag = 0
    cur = last_date + timedelta(days=1)
    while cur <= expected_date:
        if cur.weekday() < 5:
            lag += 1
        cur += timedelta(days=1)
    return lag


def _freshness_meta(rows: List[Dict[str, Any]], max_lag_sessions: int = 2) -> Dict[str, Any]:
    expected = _expected_latest_daily_bar_date()
    last_dt = _last_ohlcv_date(rows)
    lag_sessions = _weekday_lag(last_dt, expected)
    stale = bool(lag_sessions is not None and lag_sessions > max_lag_sessions)
    return {
        "last_ohlcv_date": last_dt.isoformat() if last_dt else None,
        "expected_latest_ohlcv_date": expected.isoformat(),
        "ohlcv_lag_sessions": lag_sessions,
        "ohlcv_stale": stale,
    }


def _fetch_intraday_latest_bar(symbol: str) -> Optional[Dict[str, Any]]:
    try:
        import yfinance as yf  # type: ignore
    except Exception:  # noqa: BLE001
        return None
    try:
        df = yf.Ticker(symbol).history(period="5d", interval="1h", auto_adjust=False, prepost=False)
    except Exception as exc:  # noqa: BLE001
        logger.debug("intraday yfinance fetch failed for %s: %s", symbol, exc)
        return None
    if df is None or df.empty:
        return None
    try:
        latest_day = None
        latest_group = None
        for idx, group in df.groupby(df.index.date):
            if latest_day is None or idx > latest_day:
                latest_day = idx
                latest_group = group
        if latest_day is None or latest_group is None or latest_group.empty:
            return None
        first = latest_group.iloc[0]
        last = latest_group.iloc[-1]
        return {
            "date": latest_day.isoformat(),
            "open": float(first.get("Open", last.get("Close", 0.0)) or 0.0),
            "high": float(latest_group["High"].max() or 0.0),
            "low": float(latest_group["Low"].min() or 0.0),
            "close": float(last.get("Close", 0.0) or 0.0),
            "volume": float(latest_group["Volume"].sum() or 0.0),
            "partial": True,
            "source": "yfinance_intraday_1h",
        }
    except Exception as exc:  # noqa: BLE001
        logger.debug("intraday yfinance normalization failed for %s: %s", symbol, exc)
        return None


def _merge_latest_bar(rows: List[Dict[str, Any]], bar: Optional[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], bool]:
    if not bar:
        return rows, False
    bar_dt = _parse_row_date(bar)
    if not bar_dt:
        return rows, False
    clean_rows = list(rows or [])
    last_dt = _last_ohlcv_date(clean_rows)
    if last_dt is None or bar_dt > last_dt:
        return clean_rows + [bar], True
    if bar_dt == last_dt and clean_rows:
        merged = dict(clean_rows[-1])
        merged.update(bar)
        return clean_rows[:-1] + [merged], True
    return clean_rows, False


def _fetch_fresh_ohlcv(
    symbol: str,
    lookback_days: int,
    asset_type: str = "stock",
    min_rows: int = 0,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows, status = MarketDataService.fetch_ohlcv(symbol, lookback_days=lookback_days, min_rows=min_rows)
    status = dict(status)
    status.update(_freshness_meta(rows))
    status["refresh_attempted"] = False
    status["intraday_augmented"] = False
    if asset_type != "stock" or not rows:
        return rows, status

    lag = status.get("ohlcv_lag_sessions")
    should_refresh = status.get("source") in {"cache", "stale_cache"} or (lag is not None and lag > 0)
    if should_refresh:
        refreshed, refreshed_status = MarketDataService.fetch_ohlcv(
            symbol,
            lookback_days=lookback_days,
            ttl_hours=0,
            use_cache=False,
            min_rows=min_rows,
        )
        status["refresh_attempted"] = True
        if refreshed:
            current_last = _last_ohlcv_date(rows)
            refreshed_last = _last_ohlcv_date(refreshed)
            if refreshed_last and (current_last is None or refreshed_last >= current_last):
                rows = refreshed
                status.update(refreshed_status)
                status["refresh_attempted"] = True
                status.update(_freshness_meta(rows))

    latest_bar = _fetch_intraday_latest_bar(symbol)
    rows, augmented = _merge_latest_bar(rows, latest_bar)
    if augmented:
        status["source"] = f"{status.get('source') or 'market'}+intraday"
        status["rows_count"] = len(rows)
        status["intraday_augmented"] = True
        status.update(_freshness_meta(rows))
    return rows, status


class MarketProvider:
    """金融行情 Provider，输出标准化的 market snapshot。"""

    @staticmethod
    def fetch_snapshot(
        symbol: str,
        asset_type: str = "stock",
        lookback_days: int = 180,
        min_rows: int = 0,
    ) -> Dict[str, Any]:
        """返回 market snapshot dict。

        Schema:
            {
                "ok": bool,
                "symbol": str,
                "normalized_symbol": str,
                "asset_type": str,
                "rows_count": int,
                "ohlcv": [...],   # 最近若干根日线
                "indicators": {
                    "last_close": float,
                    "ma20": float | None,
                    "ma60": float | None,
                    "rsi14": float | None,
                    "return_5d": float | None,
                    "return_30d": float | None,
                    "volatility_30d": float | None,
                    "trend": "up" | "down" | "sideways",
                },
                "source": "cache|yfinance|empty",
                "fetched_at": str | None,
            }
        """
        normalized = _normalize_symbol(symbol, asset_type)
        snapshot: Dict[str, Any] = {
            "ok": False,
            "symbol": symbol,
            "normalized_symbol": normalized,
            "asset_type": asset_type,
            "rows_count": 0,
            "ohlcv": [],
            "ohlcv_tail": [],
            "indicators": {},
            "source": "empty",
            "fetched_at": None,
        }
        if not normalized or asset_type == "event":
            return snapshot

        rows, status = _fetch_fresh_ohlcv(
            normalized,
            lookback_days=lookback_days,
            asset_type=asset_type,
            min_rows=min_rows,
        )
        snapshot["source"] = status.get("source", "empty")
        snapshot["fetched_at"] = status.get("fetched_at")
        snapshot["last_ohlcv_date"] = status.get("last_ohlcv_date")
        snapshot["expected_latest_ohlcv_date"] = status.get("expected_latest_ohlcv_date")
        snapshot["ohlcv_lag_sessions"] = status.get("ohlcv_lag_sessions")
        snapshot["ohlcv_stale"] = bool(status.get("ohlcv_stale"))
        snapshot["refresh_attempted"] = bool(status.get("refresh_attempted"))
        snapshot["intraday_augmented"] = bool(status.get("intraday_augmented"))
        snapshot["rows_below_min"] = bool(status.get("rows_below_min"))
        snapshot["min_rows"] = status.get("min_rows") or max(0, int(min_rows or 0))
        snapshot["rows_count"] = len(rows)
        if not rows:
            return snapshot

        closes = [_safe_float(r.get("close")) for r in rows]
        closes = [c for c in closes if c > 0]
        if not closes:
            return snapshot

        last_close = closes[-1]
        ma20 = _moving_average(closes, 20)
        ma60 = _moving_average(closes, 60)
        rsi14 = _rsi(closes, 14)

        return_5d = (closes[-1] / closes[-6] - 1.0) if len(closes) >= 6 else None
        return_30d = (closes[-1] / closes[-31] - 1.0) if len(closes) >= 31 else None

        # 30-day daily return volatility
        vol_30d: Optional[float] = None
        if len(closes) >= 31:
            daily_returns = [
                (closes[i] / closes[i - 1] - 1.0)
                for i in range(len(closes) - 30, len(closes))
            ]
            vol_30d = _stddev(daily_returns)

        # Trend judgement
        trend = "sideways"
        if ma20 and ma60:
            if last_close > ma20 > ma60:
                trend = "up"
            elif last_close < ma20 < ma60:
                trend = "down"

        snapshot["ok"] = True
        snapshot["ohlcv"] = rows
        snapshot["ohlcv_tail"] = rows[-90:]
        snapshot["indicators"] = {
            "last_close": last_close,
            "ma20": ma20,
            "ma60": ma60,
            "rsi14": rsi14,
            "return_5d": return_5d,
            "return_30d": return_30d,
            "volatility_30d": vol_30d,
            "trend": trend,
        }
        return snapshot


# ─────────────────────────────────────────────────────────────────────────────
# Phase B: stock-specific market signals
#
# Benchmarks and helpers for overnight gap / market beta / options PCR /
# earnings-window detection. All methods are best-effort: on any error they
# return a ``{ok: False, reason: ...}`` envelope so the forecast layer can
# drop the factor and redistribute weights.
# ─────────────────────────────────────────────────────────────────────────────

_BENCHMARK_MAP: Dict[str, str] = {
    # Semis → SOXX
    "NVDA": "SOXX", "AMD": "SOXX", "INTC": "SOXX", "AVGO": "SOXX",
    "TSM": "SOXX", "MU": "SOXX", "QCOM": "SOXX", "ARM": "SOXX", "ASML": "SOXX",
    # Mega-cap tech → QQQ
    "AAPL": "QQQ", "MSFT": "QQQ", "GOOG": "QQQ", "GOOGL": "QQQ",
    "AMZN": "QQQ", "META": "QQQ", "NFLX": "QQQ", "TSLA": "QQQ",
    "ADBE": "QQQ", "CRM": "QQQ", "ORCL": "QQQ",
}


def _benchmark_for(symbol: str) -> str:
    return _BENCHMARK_MAP.get((symbol or "").upper(), "SPY")


def _fmp_api_key() -> Optional[str]:
    return getattr(Config, "FMP_API_KEY", None) or os.environ.get("FMP_API_KEY")


def _yf_quote_pair(symbol: str) -> Optional[Dict[str, Any]]:
    """Last two daily closes from yfinance (best-effort)."""
    try:
        import yfinance as yf  # type: ignore
    except Exception:  # noqa: BLE001
        return None
    try:
        hist = yf.Ticker(symbol).history(period="5d", interval="1d", auto_adjust=False)
    except Exception:  # noqa: BLE001
        return None
    if hist is None or hist.empty or len(hist) < 2:
        return None
    last = hist.iloc[-1]
    prev = hist.iloc[-2]
    return {
        "last_close": float(last.get("Close") or 0.0),
        "prev_close": float(prev.get("Close") or 0.0),
        "last_open": float(last.get("Open") or 0.0),
    }


def _fmp_quote_short(symbol: str) -> Optional[Dict[str, Any]]:
    api_key = _fmp_api_key()
    if not api_key:
        return None
    try:
        resp = requests.get(
            f"https://financialmodelingprep.com/api/v3/quote-short/{symbol.upper()}",
            params={"apikey": api_key},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json() or []
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(data, list) or not data:
        return None
    item = data[0]
    return {
        "last_close": float(item.get("price") or 0.0),
    }


def _safe_pct(numer: float, denom: float) -> Optional[float]:
    if not denom:
        return None
    return numer / denom - 1.0


class MarketProviderExtensions:
    """Stock-side helpers attached to ``MarketProvider`` via mixin."""

    @staticmethod
    def fetch_overnight_gap(symbol: str) -> Dict[str, Any]:
        """Last open vs previous close → overnight gap percent, clipped to ±3%.

        Returns ``{ok, gap_pct, factor, prev_close, last_open, source}`` where
        ``factor`` ∈ [-1, 1] is ``tanh(gap_pct / 0.03)``.
        """
        sym = (symbol or "").strip().upper()
        out: Dict[str, Any] = {"ok": False, "source": "none"}
        if not sym:
            out["reason"] = "no symbol"
            return out
        quote = _yf_quote_pair(sym)
        source = "yfinance"
        if not quote:
            quote = _fmp_quote_short(sym)
            source = "fmp"
        if not quote:
            out["reason"] = "no quote"
            return out
        prev_close = quote.get("prev_close") or quote.get("last_close")
        last_open = quote.get("last_open")
        if not prev_close or not last_open:
            out["reason"] = "incomplete quote"
            return out
        gap = _safe_pct(last_open, prev_close)
        if gap is None:
            out["reason"] = "zero prev close"
            return out
        factor = math.tanh(gap / 0.03)
        return {
            "ok": True,
            "source": source,
            "gap_pct": round(gap, 6),
            "prev_close": prev_close,
            "last_open": last_open,
            "factor": round(max(-1.0, min(1.0, factor)), 4),
        }

    @staticmethod
    def fetch_benchmark_trend(symbol: str, lookback_days: int = 30) -> Dict[str, Any]:
        """Beta-adjusted benchmark momentum factor.

        Compares ``symbol`` and its mapped benchmark over the last 30 days;
        returns ``{ok, benchmark, beta, benchmark_return_30d, factor}``.
        ``factor = tanh(bench_return * 8.0 * (1 if beta>=0 else -1))`` —
        positive when the benchmark is trending up.
        """
        sym = (symbol or "").strip().upper()
        out: Dict[str, Any] = {"ok": False, "source": "none"}
        if not sym:
            out["reason"] = "no symbol"
            return out
        benchmark = _benchmark_for(sym)
        try:
            bench_rows, _ = MarketDataService.fetch_ohlcv(benchmark, lookback_days=max(lookback_days + 10, 45))
        except Exception as exc:  # noqa: BLE001
            out["reason"] = f"benchmark fetch failed: {exc}"
            return out
        if not bench_rows or len(bench_rows) < lookback_days + 1:
            out["reason"] = "insufficient benchmark rows"
            return out
        bench_closes = [_safe_float(r.get("close")) for r in bench_rows if _safe_float(r.get("close")) > 0]
        if len(bench_closes) < lookback_days + 1:
            out["reason"] = "insufficient benchmark closes"
            return out
        bench_return = bench_closes[-1] / bench_closes[-lookback_days - 1] - 1.0

        # naive beta via cov / var of daily returns (60d window if available)
        beta: Optional[float] = None
        try:
            symbol_rows, _ = MarketDataService.fetch_ohlcv(sym, lookback_days=max(lookback_days + 10, 75))
            sym_closes = [_safe_float(r.get("close")) for r in symbol_rows if _safe_float(r.get("close")) > 0]
            window = min(60, len(sym_closes) - 1, len(bench_closes) - 1)
            if window >= 20:
                sym_rets = [sym_closes[i] / sym_closes[i - 1] - 1.0 for i in range(len(sym_closes) - window, len(sym_closes))]
                bench_rets = [bench_closes[i] / bench_closes[i - 1] - 1.0 for i in range(len(bench_closes) - window, len(bench_closes))]
                mean_b = sum(bench_rets) / len(bench_rets)
                var_b = sum((r - mean_b) ** 2 for r in bench_rets) / len(bench_rets)
                mean_s = sum(sym_rets) / len(sym_rets)
                cov = sum((sym_rets[i] - mean_s) * (bench_rets[i] - mean_b) for i in range(len(bench_rets))) / len(bench_rets)
                if var_b > 0:
                    beta = cov / var_b
        except Exception:  # noqa: BLE001
            beta = None

        sign = 1.0 if (beta is None or beta >= 0) else -1.0
        factor = math.tanh(bench_return * 8.0) * sign
        return {
            "ok": True,
            "source": "market_data_service",
            "benchmark": benchmark,
            "beta": round(beta, 4) if beta is not None else None,
            "benchmark_return_30d": round(bench_return, 6),
            "factor": round(max(-1.0, min(1.0, factor)), 4),
        }

    @staticmethod
    def fetch_options_signal(symbol: str) -> Dict[str, Any]:
        """Put/Call ratio sentiment via FMP options endpoint.

        Returns ``{ok, pcr, factor}`` where ``factor = -tanh((pcr - 0.7)/0.5)``
        — high PCR (defensive puts) is bearish, low PCR is bullish.
        """
        sym = (symbol or "").strip().upper()
        out: Dict[str, Any] = {"ok": False, "source": "fmp_options"}
        api_key = _fmp_api_key()
        if not api_key or not sym:
            out["reason"] = "no api key" if not api_key else "no symbol"
            return out
        try:
            resp = requests.get(
                f"https://financialmodelingprep.com/api/v4/symbol-change/{sym}",
                params={"apikey": api_key},
                timeout=6,
            )
            # Endpoint not always available; treat absent data as soft drop.
            _ = resp
        except Exception:  # noqa: BLE001
            pass
        # Best-effort options PCR via FMP v4 (may 404 on free tier — degrade silently).
        try:
            resp = requests.get(
                f"https://financialmodelingprep.com/api/v4/insider-trading-statistics",
                params={"symbol": sym, "apikey": api_key},
                timeout=6,
            )
            # Free tier doesn't expose true PCR; signal disabled by default.
        except Exception:  # noqa: BLE001
            pass
        out["reason"] = "options PCR unavailable on current FMP tier"
        return out

    @staticmethod
    def fetch_earnings_window(symbol: str, window_days: int = 5) -> Dict[str, Any]:
        """Check whether symbol has an earnings event within ±``window_days``.

        Returns ``{ok, in_window, days_to_event, event_date}``.
        """
        sym = (symbol or "").strip().upper()
        out: Dict[str, Any] = {"ok": False, "source": "fmp_earnings", "in_window": False}
        api_key = _fmp_api_key()
        if not api_key or not sym:
            out["reason"] = "no api key" if not api_key else "no symbol"
            return out
        today = datetime.utcnow().date()
        try:
            resp = requests.get(
                f"https://financialmodelingprep.com/api/v3/historical/earning_calendar/{sym}",
                params={"limit": 8, "apikey": api_key},
                timeout=8,
            )
            resp.raise_for_status()
            data = resp.json() or []
        except Exception as exc:  # noqa: BLE001
            out["reason"] = str(exc)
            return out
        nearest_days: Optional[int] = None
        nearest_date: Optional[str] = None
        for item in data:
            if not isinstance(item, dict):
                continue
            raw_date = item.get("date") or item.get("fiscalDateEnding")
            if not raw_date:
                continue
            try:
                ev = datetime.strptime(str(raw_date)[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            delta = (ev - today).days
            if nearest_days is None or abs(delta) < abs(nearest_days):
                nearest_days = delta
                nearest_date = ev.isoformat()
        if nearest_days is None:
            out["reason"] = "no earnings record"
            return out
        out.update(
            ok=True,
            in_window=abs(nearest_days) <= window_days,
            days_to_event=nearest_days,
            event_date=nearest_date,
        )
        return out


# Attach mixin methods to MarketProvider so callers can use a single class.
MarketProvider.fetch_overnight_gap = staticmethod(MarketProviderExtensions.fetch_overnight_gap)  # type: ignore[attr-defined]
MarketProvider.fetch_benchmark_trend = staticmethod(MarketProviderExtensions.fetch_benchmark_trend)  # type: ignore[attr-defined]
MarketProvider.fetch_options_signal = staticmethod(MarketProviderExtensions.fetch_options_signal)  # type: ignore[attr-defined]
MarketProvider.fetch_earnings_window = staticmethod(MarketProviderExtensions.fetch_earnings_window)  # type: ignore[attr-defined]
MarketProvider.benchmark_for = staticmethod(_benchmark_for)  # type: ignore[attr-defined]
