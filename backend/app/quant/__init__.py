"""FinRex Quant subsystem (Two-Tower + Meta-Model Hybrid Alpha).

All heavy dependencies (pyqlib, lightgbm, vectorbt, akshare, ccxt, shap)
are imported lazily inside the modules that need them so that importing
`app.quant` does NOT pull these libs into the main FinRex process unless
a `/api/quant/*` route is actually invoked.
"""

__all__ = ["config"]
