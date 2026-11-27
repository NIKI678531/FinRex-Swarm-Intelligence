"""Vectorized backtester producing equity curve + trade markers for UI.

We keep this fully self-contained (does not call vectorbt) so the API can serve
broker data even when vectorbt is not installed. The accounting model supports
long, flat, and short targets with explicit cash and mark-to-market equity.
"""

from __future__ import annotations


def simulate(
    close,
    signal,
    initial_cash: float = 10000.0,
    fee_bps: float = 5.0,
    exposure: float = 0.95,
    allow_short: bool = True,
    signal_threshold: float = 0.0,
):
    """Simple long/flat/short simulator on daily close prices.

    Returns a dict with:
      equity_curve: list of {ts, cash, value, position_side, position_units}
      trades: list of {ts, side, price, pnl, kind}
      summary: scalar metrics
    """
    import numpy as np
    import pandas as pd

    df = pd.concat([close.rename("close"), signal.rename("sig")], axis=1).dropna()
    fee_rate = max(float(fee_bps), 0.0) / 10000.0
    exposure = min(max(float(exposure), 0.0), 1.0)
    signal_threshold = max(float(signal_threshold), 0.0)

    pos = 0  # -1 short, 0 flat, 1 long
    cash = float(initial_cash)
    units = 0.0
    entry_price = None
    entry_fee = 0.0
    equity_curve = []
    trades = []
    trade_log = []
    open_trade = None

    def side_name(position: int) -> str:
        if position > 0:
            return "long"
        if position < 0:
            return "short"
        return "flat"

    def marked_value(price: float) -> float:
        if pos > 0:
            return cash + units * price
        if pos < 0:
            return cash - units * price
        return cash

    for bar_idx, (ts, row) in enumerate(df.iterrows()):
        price = float(row["close"])
        raw_signal = float(row["sig"])
        target = 0 if abs(raw_signal) < signal_threshold else int(np.sign(raw_signal))
        if target < 0 and not allow_short:
            target = 0

        if target != pos:
            if pos != 0 and units > 0 and entry_price is not None:
                notional = units * price
                exit_fee = notional * fee_rate
                if pos > 0:
                    cash += notional - exit_fee
                    gross_pnl = (price - entry_price) * units
                else:
                    cash -= notional + exit_fee
                    gross_pnl = (entry_price - price) * units
                pnl = gross_pnl - entry_fee - exit_fee
                trades.append({
                    "ts": ts.isoformat(),
                    "side": "close",
                    "price": price,
                    "pnl": float(pnl),
                    "gross_pnl": float(gross_pnl),
                    "fee": float(exit_fee),
                    "position_side": side_name(pos),
                    "units": float(units),
                    "cash": float(cash),
                    "value": float(cash),
                    "kind": "positive" if pnl >= 0 else "negative",
                })
                if open_trade is not None:
                    entry_cash = float(open_trade.get("entry_notional") or 0.0) + float(open_trade.get("entry_fee") or 0.0)
                    open_trade.update({
                        "status": "closed",
                        "exit_ts": ts.isoformat(),
                        "exit_price": price,
                        "exit_signal": raw_signal,
                        "exit_fee": float(exit_fee),
                        "exit_notional": float(notional),
                        "gross_pnl": float(gross_pnl),
                        "net_pnl": float(pnl),
                        "return_pct": float(pnl / entry_cash) if entry_cash > 0 else None,
                        "holding_bars": int(max(0, bar_idx - int(open_trade.get("entry_bar", bar_idx)))),
                    })
                    trade_log.append(open_trade)
                pos = 0
                units = 0.0
                entry_price = None
                entry_fee = 0.0
                open_trade = None

            if target != 0 and cash > 0 and price > 0:
                notional = cash * exposure
                units = notional / price
                entry_fee = notional * fee_rate
                if target > 0:
                    cash -= notional + entry_fee
                else:
                    cash += notional - entry_fee
                pos = target
                entry_price = price
                trades.append({
                    "ts": ts.isoformat(),
                    "side": "buy" if target > 0 else "sell",
                    "price": price,
                    "pnl": 0.0,
                    "fee": float(entry_fee),
                    "position_side": side_name(pos),
                    "units": float(units),
                    "cash": float(cash),
                    "value": float(marked_value(price)),
                    "kind": "entry",
                })
                open_trade = {
                    "status": "open",
                    "side": side_name(pos),
                    "entry_ts": ts.isoformat(),
                    "entry_price": price,
                    "entry_signal": raw_signal,
                    "entry_fee": float(entry_fee),
                    "entry_notional": float(notional),
                    "units": float(units),
                    "entry_bar": int(bar_idx),
                }

        value = marked_value(price)
        equity_curve.append({
            "ts": ts.isoformat(),
            "cash": float(cash),
            "value": float(value),
            "price": price,
            "position_side": side_name(pos),
            "position_units": float(units),
            "signal": float(row["sig"]),
        })

    if not equity_curve:
        return {"equity_curve": [], "trades": [], "trade_log": [], "summary": {}}

    if open_trade is not None:
        mark_price = float(df["close"].iloc[-1])
        mark_notional = float(units * mark_price)
        if pos > 0:
            gross_pnl = (mark_price - float(open_trade.get("entry_price") or mark_price)) * units
        else:
            gross_pnl = (float(open_trade.get("entry_price") or mark_price) - mark_price) * units
        open_trade.update({
            "mark_ts": df.index[-1].isoformat(),
            "mark_price": mark_price,
            "mark_notional": mark_notional,
            "unrealized_pnl": float(gross_pnl - float(open_trade.get("entry_fee") or 0.0)),
            "holding_bars": int(max(0, len(df) - 1 - int(open_trade.get("entry_bar", len(df) - 1)))),
        })
        trade_log.append(open_trade)

    final_value = equity_curve[-1]["value"]
    total_return = (final_value / initial_cash) - 1.0 if initial_cash else 0.0
    closed_trades = [t for t in trades if t["kind"] != "entry"]
    closed_log = [t for t in trade_log if t.get("status") == "closed"]
    values = pd.Series([p["value"] for p in equity_curve], index=df.index)
    strategy_returns = values.pct_change().dropna()
    benchmark_returns = df["close"].pct_change().dropna()
    ann_factor = 252.0
    n_periods = max(len(strategy_returns), 1)
    annual_return = (1.0 + total_return) ** (ann_factor / n_periods) - 1.0 if total_return > -1 else None
    ann_vol = float(strategy_returns.std(ddof=0) * np.sqrt(ann_factor)) if len(strategy_returns) > 1 else 0.0
    benchmark_total = (float(df["close"].iloc[-1]) / float(df["close"].iloc[0])) - 1.0 if float(df["close"].iloc[0]) else 0.0
    benchmark_ann_return = (1.0 + benchmark_total) ** (ann_factor / n_periods) - 1.0 if benchmark_total > -1 else None
    aligned = pd.concat([strategy_returns.rename("strategy"), benchmark_returns.rename("benchmark")], axis=1).dropna()
    beta = None
    if len(aligned) > 1 and float(aligned["benchmark"].var(ddof=0)) > 0:
        beta = float(aligned["strategy"].cov(aligned["benchmark"], ddof=0) / aligned["benchmark"].var(ddof=0))
    peak = values.cummax()
    drawdown = values / peak - 1.0
    max_drawdown = float(drawdown.min()) if len(drawdown) else 0.0
    wins = [float(t.get("net_pnl") or 0.0) for t in closed_log if float(t.get("net_pnl") or 0.0) > 0]
    losses = [float(t.get("net_pnl") or 0.0) for t in closed_log if float(t.get("net_pnl") or 0.0) < 0]
    profit_factor = (sum(wins) / abs(sum(losses))) if losses else (999.0 if wins else None)
    position_bars = sum(1 for p in equity_curve if p.get("position_side") != "flat")
    summary = {
        "initial_cash": float(initial_cash),
        "final_value": float(final_value),
        "total_return": float(total_return),
        "annual_return": float(annual_return) if annual_return is not None else None,
        "ann_vol": ann_vol,
        "benchmark_return": float(benchmark_total),
        "benchmark_ann_return": float(benchmark_ann_return) if benchmark_ann_return is not None else None,
        "alpha": float(annual_return - benchmark_ann_return) if annual_return is not None and benchmark_ann_return is not None else None,
        "beta": beta,
        "max_drawdown": max_drawdown,
        "calmar": float(annual_return / abs(max_drawdown)) if annual_return is not None and max_drawdown < 0 else None,
        "profit_factor": float(profit_factor) if profit_factor is not None else None,
        "exposure": float(position_bars / len(equity_curve)) if equity_curve else 0.0,
        "turnover_proxy": float(len([t for t in trades if t["kind"] == "entry"]) / max(len(equity_curve), 1)),
        "num_trades": int(len([t for t in trades if t["kind"] == "entry"])),
        "closed_trades": int(len(closed_log) or len(closed_trades)),
        "avg_holding_days": float(sum(float(t.get("holding_bars") or 0.0) for t in closed_log) / len(closed_log)) if closed_log else 0.0,
        "total_closed_pnl": float(sum(t.get("pnl", 0.0) for t in closed_trades)),
    }

    # Phase 4 — optional vectorbt enrichment (does not replace summary keys above).
    vbt_stats = None
    try:
        import vectorbt as vbt  # type: ignore
        # Build entries/exits from `trades` list
        entry_ts = {t["ts"] for t in trades if t.get("kind") == "entry"}
        exit_ts = {t["ts"] for t in trades if t.get("kind") in ("positive", "negative")}
        index = [p["ts"] for p in equity_curve]
        entries = pd.Series([ts in entry_ts for ts in index], index=pd.to_datetime(index))
        exits = pd.Series([ts in exit_ts for ts in index], index=pd.to_datetime(index))
        prices = pd.Series([p["price"] for p in equity_curve], index=pd.to_datetime(index))
        if entries.any():
            pf = vbt.Portfolio.from_signals(
                close=prices,
                entries=entries,
                exits=exits,
                init_cash=float(initial_cash),
                fees=fee_rate,
                freq="1D",
            )
            raw = pf.stats()
            # Stringify keys + convert numpy scalars
            vbt_stats = {}
            for k, v in raw.items():
                try:
                    if hasattr(v, "item"):
                        v = v.item()
                    elif isinstance(v, (pd.Timestamp,)):
                        v = v.isoformat()
                    vbt_stats[str(k)] = v
                except Exception:
                    vbt_stats[str(k)] = str(v)
    except Exception:
        vbt_stats = None

    return {
        "equity_curve": equity_curve,
        "trades": trades,
        "trade_log": trade_log,
        "summary": summary,
        "vbt_stats": vbt_stats,
    }
