from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.config import Config
import app.services.zep_tools as zep_tools
from app.services.zep_tools import ZepToolsService


class TestZepToolsCacheFallback(unittest.TestCase):
    def setUp(self):
        self._old_upload_folder = Config.UPLOAD_FOLDER
        self._old_fetch_nodes = zep_tools.fetch_all_nodes
        self._old_fetch_edges = zep_tools.fetch_all_edges
        self.temp_dir = tempfile.TemporaryDirectory()
        Config.UPLOAD_FOLDER = self.temp_dir.name

        graph_cache_dir = os.path.join(Config.UPLOAD_FOLDER, "graph_cache")
        os.makedirs(graph_cache_dir, exist_ok=True)
        self.graph_id = "finrex_cached"
        with open(os.path.join(graph_cache_dir, f"{self.graph_id}.json"), "w", encoding="utf-8") as f:
            json.dump(
                {
                    "graph_id": self.graph_id,
                    "nodes": [
                        {
                            "uuid": "node-1",
                            "name": "NVDA",
                            "labels": ["Company"],
                            "summary": "AI chip demand is rising.",
                            "attributes": {"ticker": "NVDA"},
                        }
                    ],
                    "edges": [
                        {
                            "uuid": "edge-1",
                            "name": "AFFECTS",
                            "fact": "AI chip demand affects NVDA attention.",
                            "source_node_uuid": "node-1",
                            "target_node_uuid": "node-1",
                            "source_node_name": "NVDA",
                            "target_node_name": "NVDA",
                        }
                    ],
                },
                f,
            )

        self.service = object.__new__(ZepToolsService)
        self.service.client = object()
        self.service._graph_cache_by_id = {}
        self.service._remote_disabled_until = 0.0

    def tearDown(self):
        zep_tools.fetch_all_nodes = self._old_fetch_nodes
        zep_tools.fetch_all_edges = self._old_fetch_edges
        Config.UPLOAD_FOLDER = self._old_upload_folder
        self.temp_dir.cleanup()

    def test_nodes_fall_back_to_cache_after_zep_rate_limit(self):
        def fail_nodes(*args, **kwargs):
            raise RuntimeError("status_code: 429, body: Rate limit exceeded")

        zep_tools.fetch_all_nodes = fail_nodes

        nodes = self.service.get_all_nodes(self.graph_id)

        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0].name, "NVDA")
        self.assertGreater(self.service._remote_disabled_until, 0)

    def test_search_uses_cached_edges_while_remote_is_backing_off(self):
        def fail_edges(*args, **kwargs):
            raise AssertionError("remote edge fetch should not run while backing off")

        zep_tools.fetch_all_edges = fail_edges
        self.service._remote_disabled_until = 9999999999

        result = self.service.search_graph(self.graph_id, "NVDA chip demand", limit=5)

        self.assertEqual(result.total_count, 1)
        self.assertIn("NVDA attention", result.facts[0])


if __name__ == "__main__":
    unittest.main()
