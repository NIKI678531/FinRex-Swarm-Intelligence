"""Performance metrics — self-contained, no dependency on markettime_live.

All inputs are pandas Series of daily strategy returns (decimal, e.g. 0.012).
"""

from __future__ import annotations


def annualization_factor(freq: str = "1d") -> float:
    return {"1d": 252.0, "1h": 252 * 24}.get(freq, 252.0)


def compute_performance(returns, freq: str = "1d", benchmark_returns=None) -> dict:
    import math
    import numpy as np
    import pandas as pd

    r = returns.dropna()
    if len(r) == 0:
        return _empty()
    af = annualization_factor(freq)
    mean = float(r.mean())
    std = float(r.std(ddof=0)) or 1e-9
    downside = r[r < 0]
    dstd = (float(downside.std(ddof=0)) if len(downside) else 0.0) or 1e-9
    sharpe = mean / std * math.sqrt(af)
    sortino = mean / dstd * math.sqrt(af)
    equity = (1.0 + r).cumprod()
    peak = equity.cummax()
    dd = (equity / peak - 1.0).min()
    hit = float((r > 0).mean())
    turnover = float(r.abs().mean())
    out = {
        "ann_return": (1.0 + mean) ** af - 1.0,
        "ann_vol": std * math.sqrt(af),
        "sharpe": float(sharpe),
        "sortino": float(sortino),
        "max_drawdown": float(dd),
        "hit_ratio": hit,
        "turnover_proxy": turnover,
        "n_periods": int(len(r)),
    }
    if benchmark_returns is not None:
        aligned = pd.concat([r.rename("strategy"), benchmark_returns.rename("benchmark")], axis=1).dropna()
        if not aligned.empty:
            b = aligned["benchmark"]
            b_mean = float(b.mean())
            b_var = float(b.var(ddof=0))
            b_ann_return = (1.0 + b_mean) ** af - 1.0
            beta = None
            if b_var > 0 and len(aligned) > 1:
                beta = float(aligned["strategy"].cov(b, ddof=0) / b_var)
            out.update({
                "benchmark_ann_return": float(b_ann_return),
                "alpha": float(out["ann_return"] - b_ann_return),
                "beta": beta,
            })

    # merge professional metrics (pro_*) — additive, original keys untouched
    try:
        from .pro_metrics import build_pro_metrics
        out.update(build_pro_metrics(r, benchmark_returns=benchmark_returns, freq=freq))
    except Exception:  # noqa: BLE001
        pass
    return out


def compute_ic(signal, forward_return) -> dict:
    """Information Coefficient and IR."""
    import numpy as np
    import pandas as pd

    df = pd.concat([signal.rename("signal"), forward_return.rename("ret")], axis=1).dropna()
    if df.empty:
        return {"ic_mean": 0.0, "ic_ir": 0.0, "ic_t": 0.0, "n": 0}
    # Rolling 20-day Spearman IC
    ics = []
    win = 20
    for i in range(win, len(df) + 1):
        block = df.iloc[i - win:i]
        if block["signal"].nunique() < 2:
            continue
        ics.append(block.corr(method="spearman").iloc[0, 1])
    if not ics:
        c = df.corr(method="spearman").iloc[0, 1]
        return {"ic_mean": float(c), "ic_ir": 0.0, "ic_t": 0.0, "n": len(df)}
    ic_arr = pd.Series(ics).dropna()
    mean = float(ic_arr.mean())
    std = float(ic_arr.std(ddof=0)) or 1e-9
    return {
        "ic_mean": mean,
        "ic_ir": mean / std,
        "ic_t": mean / (std / (len(ic_arr) ** 0.5)),
        "n": int(len(df)),
    }


def _empty():
    return {
        "ann_return": 0.0, "ann_vol": 0.0, "sharpe": 0.0, "sortino": 0.0,
        "max_drawdown": 0.0, "hit_ratio": 0.0, "turnover_proxy": 0.0,
        "n_periods": 0, "benchmark_ann_return": 0.0, "alpha": 0.0, "beta": None,
    }
