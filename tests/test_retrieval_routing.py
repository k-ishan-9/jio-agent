"""
tests/test_retrieval_routing.py — unit tests for the two retrieval tools in
retrieval/tools.py: the SQL path (query_jio_plans, exact structured lookups)
and the vector path (search_jio_knowledge, semantic FAQ search). These are
the two tools the ADK agent routes between per-question (see
agent/adk_agent.py) — this file tests each path in isolation rather than the
agent's routing decision itself, which requires a live LLM call.

Uses a temporary SQLite DB and a small in-memory FAISS index instead of the
real data files / Gemini embeddings, so tests run offline and fast.
"""

import asyncio
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import faiss
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import EMBEDDING_DIM
from retrieval import tools as retrieval_tools


def _make_test_db(path: Path):
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT, section TEXT, category TEXT, price REAL,
            validity TEXT, data_gb REAL, speed_mbps REAL,
            subscriptions TEXT, description TEXT, url TEXT
        )
    """)
    rows = [
        ("Prepaid 299", "mobile_plans", "prepaid", 299.0, "28 days", 2.0, None, "", "Basic recharge", "http://x/299"),
        ("Prepaid 479", "mobile_plans", "prepaid", 479.0, "28 days", 2.0, None, "Netflix", "Mid-tier w/ Netflix", "http://x/479"),
        ("Postpaid 999", "mobile_plans", "postpaid", 999.0, "Monthly", 100.0, None, "Netflix,Prime", "High-end postpaid", "http://x/999"),
        ("Fiber 1499", "fiber", "fiber_home", 1499.0, "Monthly", None, 300.0, "", "300 Mbps home fiber", "http://x/fiber1499"),
    ]
    conn.executemany(
        "INSERT INTO plans (title, section, category, price, validity, data_gb, speed_mbps, subscriptions, description, url) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()


class TestSqlPlanRouting(unittest.TestCase):
    """find_jio_plans should hit this path for exact price/data/OTT questions."""

    def setUp(self):
        import tempfile
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test_plans.db"
        _make_test_db(self.db_path)
        self._patcher = patch("retrieval.tools.SQLITE_DB_PATH", self.db_path)
        self._patcher.start()
        self.addCleanup(self._patcher.stop)

    def _run(self, coro):
        return asyncio.run(coro)

    def test_filters_by_max_price(self):
        results = self._run(retrieval_tools.query_jio_plans(max_price=500))
        titles = {r["title"] for r in results}
        self.assertEqual(titles, {"Prepaid 299", "Prepaid 479"})

    def test_filters_by_subscription(self):
        results = self._run(retrieval_tools.query_jio_plans(subscription="Netflix"))
        titles = {r["title"] for r in results}
        self.assertEqual(titles, {"Prepaid 479", "Postpaid 999"})

    def test_filters_by_section(self):
        results = self._run(retrieval_tools.query_jio_plans(section="fiber"))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Fiber 1499")

    def test_no_match_returns_empty_list_not_error(self):
        """A no_results answer must be a clean empty list, not an exception —
        this is the exact-fact guarantee the SQL path exists for."""
        results = self._run(retrieval_tools.query_jio_plans(max_price=1))
        self.assertEqual(results, [])

    def test_results_ordered_by_price_ascending(self):
        results = self._run(retrieval_tools.query_jio_plans())
        prices = [r["price"] for r in results]
        self.assertEqual(prices, sorted(prices))


class TestVectorFaqRouting(unittest.TestCase):
    """search_jio_faq_and_info should hit this path for semantic/how-to questions."""

    def setUp(self):
        metadata = {
            "0": {"section": "faq", "category": "porting", "title": "How to port your number",
                  "content": "Visit any Jio store with your ID proof to port.", "url": "http://x/port"},
            "1": {"section": "faq", "category": "billing", "title": "How to pay your bill",
                  "content": "Use the MyJio app to pay online.", "url": "http://x/bill"},
            "2": {"section": "business", "category": "enterprise", "title": "Jio Business Solutions",
                  "content": "Enterprise connectivity and cloud services.", "url": "http://x/biz"},
        }
        vectors = np.eye(3, EMBEDDING_DIM, dtype="float32")  # 3 orthogonal unit vectors
        faiss.normalize_L2(vectors)
        index = faiss.IndexFlatIP(EMBEDDING_DIM)
        index.add(vectors)

        retrieval_tools._faiss_index = index
        retrieval_tools._faiss_metadata = metadata
        self._query_vecs = {
            "porting question": vectors[0:1].copy(),
            "billing question": vectors[1:2].copy(),
            "business question": vectors[2:3].copy(),
        }

    def tearDown(self):
        retrieval_tools._faiss_index = None
        retrieval_tools._faiss_metadata = None

    def _search(self, query_key, **kwargs):
        vec = self._query_vecs[query_key]
        with patch.object(retrieval_tools, "get_client") as mock_get_client:
            mock_client = mock_get_client.return_value
            mock_client.models.embed_content.return_value = type(
                "R", (), {"embeddings": [type("E", (), {"values": vec[0].tolist()})()]}
            )()
            return asyncio.run(retrieval_tools.search_jio_knowledge(query_key, **kwargs))

    def test_semantic_match_returns_best_result_first(self):
        results = self._search("porting question", top_k=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "How to port your number")

    def test_section_filter_restricts_results(self):
        results = self._search("business question", top_k=3, section_filter="business")
        self.assertTrue(all(r["section"] == "business" for r in results))
        self.assertTrue(any(r["title"] == "Jio Business Solutions" for r in results))

    def test_empty_index_returns_empty_list(self):
        retrieval_tools._faiss_index = None
        retrieval_tools._faiss_metadata = None
        results = self._search("porting question", top_k=1)
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
