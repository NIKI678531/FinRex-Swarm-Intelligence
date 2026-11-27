"""Unit tests for weekly paper-bet edge and Kelly sizing."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import Config

Config.VALIDATION_DB_URL = "sqlite:///:memory:"

from app.services.validation.weekly_engine import _kelly_stake, build_weekly_stake_decisions


def test_kelly_stake_uses_standard_binary_formula():
    # Model prob below entry price => non-positive Kelly => no stake.
    assert _kelly_stake(model_prob=0.19, entry_prob=0.20, kelly_fraction=0.25) == 0.0
    # f* = p - (1-p)*entry/(1-entry) = 0.25 - 0.75*0.20/0.80 = 0.0625; *0.25 = 0.015625
    assert _kelly_stake(model_prob=0.25, entry_prob=0.20, kelly_fraction=0.25) == pytest.approx(0.015625)
    # Degenerate entry price clips to zero.
    assert _kelly_stake(model_prob=0.50, entry_prob=1.0, kelly_fraction=0.25) == 0.0


def test_stake_decisions_fallback_to_baseline_and_cap_total_stake():
    bins = [
        {"index": 0, "label": "low", "prob": 0.40},
        {"index": 1, "label": "mid", "prob": 0.35},
        {"index": 2, "label": "high", "prob": 0.25},
    ]

    decisions = build_weekly_stake_decisions(
        bins,
        {},
        baseline_prob=1 / 3,
        kelly_fraction=1.0,
        max_stake_pct=0.05,
        cash=10_000.0,
    )

    assert len(decisions) == 2
    assert sum(d["stake_usd"] for d in decisions) == pytest.approx(500.0)
    assert all(d["prob_source"] == "uniform_baseline" for d in decisions)
    assert all(d["edge"] > 0 for d in decisions)
    assert all(d["expected_value"] > 0 for d in decisions)


def test_stake_decisions_prefer_polymarket_yes_price_when_available():
    bins = [
        {"index": 0, "label": "low", "prob": 0.40},
        {"index": 1, "label": "mid", "prob": 0.35},
    ]

    decisions = build_weekly_stake_decisions(
        bins,
        {0: {"prob": 0.30, "source": "polymarket_yes"}, 1: {"prob": 0.40, "source": "polymarket_yes"}},
        baseline_prob=0.50,
        kelly_fraction=0.25,
        max_stake_pct=0.05,
        cash=10_000.0,
    )

    assert len(decisions) == 1
    assert decisions[0]["bin"]["index"] == 0
    assert decisions[0]["entry_prob"] == pytest.approx(0.30)
    assert decisions[0]["prob_source"] == "polymarket_yes"
    assert decisions[0]["stake_usd"] <= 500.0
