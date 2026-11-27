from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

from flask import Flask

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.controllers import graph_bp
from app.controllers import articles


class BinanceD1DegradationTest(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(graph_bp, url_prefix="/api/graph")
        self.client = app.test_client()

    def test_binance_articles_d1_unavailable_returns_empty_success(self):
        reason = "Cloudflare D1 credentials are not authorized for this account/database."
        with patch.object(articles, "_cloudflare_d1_query", side_effect=articles.D1Unavailable(reason)):
            with patch.object(articles, "_fetch_binance_live_news", return_value=[]):
                with patch.object(articles, "_load_cached_binance_articles", return_value=[]):
                    resp = self.client.get("/api/graph/articles/binance?source=news")

        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["items"], [])
        self.assertEqual(payload["data"]["count"], 0)
        self.assertEqual(payload["data"]["data_quality"]["code"], "d1_unavailable")
        self.assertEqual(payload["data"]["data_quality"]["reason"], reason)
        self.assertEqual(payload["data"]["warning"], "")
        self.assertNotIn("api.cloudflare.com", payload["data"]["warning"])

    def test_binance_articles_d1_unavailable_uses_cache_fallback(self):
        reason = "Cloudflare D1 credentials are not authorized for this account/database."
        cached = [{
            "id": "cached-1",
            "title": "BTC cached post",
            "content": "BTC cached content",
            "date": "2026-05-13 00:27:38",
            "source": "binance_d1",
            "publish_time": 1778632058,
        }]
        with patch.object(articles, "_cloudflare_d1_query", side_effect=articles.D1Unavailable(reason)):
            with patch.object(articles, "_fetch_binance_live_news", return_value=[]):
                with patch.object(articles, "_load_cached_binance_articles", return_value=cached):
                    resp = self.client.get("/api/graph/articles/binance?source=news")

        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["items"], cached)
        self.assertEqual(payload["data"]["data_quality"]["fallback_source"], "local_jsonl_cache")
        self.assertFalse(payload["data"]["data_quality"]["source_filter_supported"])
        self.assertTrue(payload["data"]["warning"])
        self.assertIn("不是最新", payload["data"]["warning"])

    def test_binance_articles_d1_unavailable_uses_live_news_first(self):
        reason = "Cloudflare D1 credentials are not authorized for this account/database."
        live = [{
            "id": "binance-news:abc",
            "title": "Binance live update",
            "content": "Live Binance announcement",
            "date": "2026-06-01 10:00:00",
            "source": "binance_live_news",
            "publish_time": 1780293600,
        }]
        with patch.object(articles, "_cloudflare_d1_query", side_effect=articles.D1Unavailable(reason)):
            with patch.object(articles, "_fetch_binance_live_news", return_value=live):
                resp = self.client.get("/api/graph/articles/binance?source=news")

        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["items"], live)
        self.assertEqual(payload["data"]["data_quality"]["source"], "binance_public_cms")
        self.assertTrue(payload["data"]["data_quality"]["realtime"])
        self.assertTrue(payload["data"]["warning"])
        self.assertIn("公告", payload["data"]["warning"])

    def test_cloudflare_403_is_sanitized_by_endpoint(self):
        class ForbiddenResponse:
            status_code = 403

            def raise_for_status(self):
                raise AssertionError("403 should be handled before raise_for_status")

        with patch.object(articles.Config, "CLOUDFLARE_D1_ACCOUNT_ID", "account-id"):
            with patch.object(articles.Config, "CLOUDFLARE_D1_DATABASE_ID", "database-id"):
                with patch.object(articles.Config, "CLOUDFLARE_D1_API_TOKEN", "token"):
                    with patch.object(articles.requests, "post", return_value=ForbiddenResponse()):
                        with patch.object(articles, "_fetch_binance_live_news", return_value=[]):
                            with patch.object(articles, "_load_cached_binance_articles", return_value=[]):
                                resp = self.client.get("/api/graph/articles/binance?source=news")

        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        warning = payload["data"]["warning"]
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["items"], [])
        self.assertEqual(warning, "")
        self.assertIn("not authorized", payload["data"]["data_quality"]["reason"])
        self.assertNotIn("api.cloudflare.com", warning)
        self.assertNotIn("account-id", warning)
        self.assertNotIn("database-id", warning)

    def test_binance_comments_d1_unavailable_returns_empty_success(self):
        reason = "Cloudflare D1 credentials are not authorized for this account/database."
        with patch.object(articles, "_cloudflare_d1_query", side_effect=articles.D1Unavailable(reason)):
            resp = self.client.get("/api/graph/articles/binance/post-1/comments")

        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["items"], [])
        self.assertFalse(payload["data"]["comments_available"])
        self.assertEqual(payload["data"]["data_quality"]["code"], "d1_unavailable")
        self.assertNotIn("api.cloudflare.com", payload["data"]["unavailable_reason"])


if __name__ == "__main__":
    unittest.main()
