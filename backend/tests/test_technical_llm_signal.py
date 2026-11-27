from __future__ import annotations

import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.financial.technical_llm_signal import (  # noqa: E402
    build_technical_signal,
    call_technical_llm_signal,
    clear_llm_cache,
)


def _trend_rows(n=300, drift=0.004, noise=0.002, seed=11, volume_spike=False, atr_scale=0.004):
    rnd = random.Random(seed)
    rows = []
    price = 100.0
    for idx in range(n):
        ret = drift + rnd.gauss(0.0, noise)
        if idx > n - 30:
            ret += drift
        new_price = max(1.0, price * (1.0 + ret))
        high = max(price, new_price) * (1.0 + atr_scale)
        low = min(price, new_price) * (1.0 - atr_scale)
        volume = 1_000_000 * (3.0 if volume_spike and idx == n - 1 else 1.0)
        rows.append({
            "date": f"2025-01-{(idx % 28) + 1:02d}",
            "open": price,
            "high": high,
            "low": low,
            "close": new_price,
            "volume": volume,
        })
        price = new_price
    return rows


def test_technical_signal_scores_strong_up_and_down():
    up = build_technical_signal(_trend_rows(drift=0.004, volume_spike=True))
    down = build_technical_signal(_trend_rows(drift=-0.004, noise=0.002))

    assert up["ok"] is True
    assert up["status"] == "full"
    assert up["multi_indicator_score"] > 0.3
    assert down["ok"] is True
    assert down["multi_indicator_score"] < -0.2


def test_technical_signal_partial_and_insufficient_history():
    partial = build_technical_signal(_trend_rows(n=180, drift=0.001))
    insufficient = build_technical_signal(_trend_rows(n=80, drift=0.001))

    assert partial["ok"] is True
    assert partial["status"] == "partial"
    assert insufficient["ok"] is False
    assert insufficient["status"] == "insufficient_history"


def test_volume_spike_and_extreme_atr_are_reflected():
    volume = build_technical_signal(_trend_rows(drift=0.001, volume_spike=True))
    volatile = build_technical_signal(_trend_rows(drift=0.001, atr_scale=0.08))

    assert volume["indicators"]["VOL_RATIO_20"]["level"] == "strong_bullish"
    assert volatile["indicators"]["ATR_PCT_14"]["level"] == "strong_bearish"


def test_sideways_signal_stays_bounded():
    rows = []
    for idx in range(300):
        close = 100.0 + math.sin(idx / 7.0) * 0.3
        rows.append({
            "date": f"2025-02-{(idx % 28) + 1:02d}",
            "open": close,
            "high": close + 0.4,
            "low": close - 0.4,
            "close": close,
            "volume": 1_000_000,
        })
    signal = build_technical_signal(rows)

    assert signal["ok"] is True
    assert abs(signal["multi_indicator_score"]) < 0.5


def test_llm_signal_disabled_by_default(monkeypatch):
    clear_llm_cache()
    monkeypatch.delenv("STOCK_TECH_LLM_ENABLED", raising=False)
    technical = build_technical_signal(_trend_rows())
    out = call_technical_llm_signal("NVDA", _trend_rows(), 1, technical)

    assert out["ok"] is False
    assert out["enabled"] is False


def test_llm_signal_success_and_cache(monkeypatch):
    clear_llm_cache()
    monkeypatch.setenv("STOCK_TECH_LLM_ENABLED", "true")
    technical = build_technical_signal(_trend_rows())
    rows = _trend_rows()
    calls = []

    class FakeLLM:
        def chat_json(self, **kwargs):
            calls.append(kwargs)
            return {
                "score": 1.5,
                "confidence": "high",
                "reason": "momentum confirmed",
                "risk_flags": ["extended"],
            }

    first = call_technical_llm_signal("NVDA", rows, 1, technical, llm_client=FakeLLM())
    second = call_technical_llm_signal("NVDA", rows, 1, technical, llm_client=FakeLLM())

    assert first["ok"] is True
    assert first["score"] == 1.0
    assert first["confidence"] == "high"
    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    assert len(calls) == 1


def test_llm_signal_invalid_json_shape_degrades(monkeypatch):
    clear_llm_cache()
    monkeypatch.setenv("STOCK_TECH_LLM_ENABLED", "true")
    technical = build_technical_signal(_trend_rows())

    class FakeLLM:
        def chat_json(self, **kwargs):
            return {"confidence": "high", "reason": "missing score"}

    out = call_technical_llm_signal("NVDA", _trend_rows(), 1, technical, llm_client=FakeLLM())

    assert out["ok"] is False
    assert "missing numeric score" in out["reason"]
