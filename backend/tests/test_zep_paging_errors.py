from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from zep_cloud import ApiError, NotFoundError

from app.utils.zep_paging import (
    ZepGraphNotFoundError,
    fetch_all_edges,
    fetch_all_nodes,
)


class _NotFoundNodes:
    def get_by_graph_id(self, graph_id: str, **kwargs):
        raise NotFoundError(ApiError(message="not found"), headers={"x-request-id": "hidden"})


class _NotFoundEdges:
    def get_by_graph_id(self, graph_id: str, **kwargs):
        raise NotFoundError(ApiError(message="not found"), headers={"x-request-id": "hidden"})


class _Graph:
    node = _NotFoundNodes()
    edge = _NotFoundEdges()


class _Client:
    graph = _Graph()


class TestZepPagingErrors(unittest.TestCase):
    def test_node_404_becomes_clean_graph_error(self):
        with self.assertRaises(ZepGraphNotFoundError) as ctx:
            fetch_all_nodes(_Client(), "finrex_missing")

        self.assertEqual(ctx.exception.graph_id, "finrex_missing")
        self.assertIn("finrex_missing", str(ctx.exception))
        self.assertNotIn("headers", str(ctx.exception))

    def test_edge_404_becomes_clean_graph_error(self):
        with self.assertRaises(ZepGraphNotFoundError) as ctx:
            fetch_all_edges(_Client(), "finrex_missing")

        self.assertEqual(ctx.exception.graph_id, "finrex_missing")
        self.assertIn("finrex_missing", str(ctx.exception))
        self.assertNotIn("headers", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
