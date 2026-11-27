"""Tests for Step1 financial seed extraction used by final report generation."""

from __future__ import annotations

import os
import sys
import unittest
import types
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

zep_cloud = types.ModuleType("zep_cloud")
zep_cloud.InternalServerError = RuntimeError
zep_cloud.NotFoundError = RuntimeError
zep_client = types.ModuleType("zep_cloud.client")
zep_client.Zep = object
zep_core = types.ModuleType("zep_cloud.core")
zep_api_error = types.ModuleType("zep_cloud.core.api_error")
zep_api_error.ApiError = RuntimeError
sys.modules.setdefault("zep_cloud", zep_cloud)
sys.modules.setdefault("zep_cloud.client", zep_client)
sys.modules.setdefault("zep_cloud.core", zep_core)
sys.modules.setdefault("zep_cloud.core.api_error", zep_api_error)

from app.controllers import report as report_api


class TestFinancialSeedContext(unittest.TestCase):
    def test_structured_seed_context_splits_articles_and_comments(self):
        project = SimpleNamespace(
            project_id="proj_test",
            created_at="2026-05-26T10:00:00",
            financial_seed_context={
                "selected_articles": [
                    {
                        "title": "FMP BTC headline",
                        "content": "ETF inflow supports BTC demand",
                        "source_type": "fmp",
                        "published_at": "2026-05-26T09:30:00",
                    }
                ],
                "comments": [
                    {"text": "Binance users are bullish", "source": "binance", "post_id": "p1"}
                ],
            },
        )

        ctx = report_api._extract_financial_seed_context(project)

        self.assertEqual(len(ctx["articles"]), 1)
        self.assertEqual(ctx["articles"][0]["source"], "fmp")
        self.assertEqual(len(ctx["comments"]), 1)
        self.assertEqual(ctx["comments"][0]["source"], "binance")

    def test_text_seed_context_does_not_turn_fmp_articles_into_comments(self):
        project = SimpleNamespace(
            project_id="proj_text",
            created_at="2026-05-26T10:00:00",
            financial_seed_context=None,
        )
        extracted = """=== Market seed 1 ===
=== Source metadata ===
source_type: fmp
content_type: news

=== Simulated seed material ===
FMP article says liquidity is improving.

=== Observed comment layer ===
No real comment text was available for this seed; downstream simulation must treat reactions as Simulated, not Observed.

=== Market seed 2 ===
=== Source metadata ===
source_type: binance
content_type: post

=== Simulated seed material ===
Binance post about BTC breakout.

=== Observed comment layer ===
[1] real Binance comment text
"""

        original = report_api.ProjectManager.get_extracted_text
        report_api.ProjectManager.get_extracted_text = staticmethod(lambda project_id: extracted)
        try:
            ctx = report_api._extract_financial_seed_context(project)
        finally:
            report_api.ProjectManager.get_extracted_text = original

        self.assertEqual(len(ctx["articles"]), 2)
        self.assertEqual(len(ctx["comments"]), 1)
        self.assertEqual(ctx["articles"][0]["source"], "fmp")
        self.assertEqual(ctx["comments"][0]["text"], "real Binance comment text")


if __name__ == "__main__":
    unittest.main()
