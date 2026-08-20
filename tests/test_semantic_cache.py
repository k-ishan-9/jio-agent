"""
tests/test_semantic_cache.py — unit tests for the FAISS-backed semantic
cache (agent/semantic_cache.py): similarity-threshold matching, TTL
expiry, and the clear() hook used by the re-ingestion pipeline. Embeddings
are stubbed with fixed vectors instead of calling the real Gemini API, so
tests run offline and deterministically.
"""

import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import EMBEDDING_DIM
from agent.semantic_cache import SemanticCache


def _vec(seed: float) -> np.ndarray:
    """Deterministic L2-normalized vector so cosine similarity (via FAISS
    inner product) is controllable: identical seeds -> similarity 1.0,
    distant seeds -> similarity ~0 (near-orthogonal in high dimensions)."""
    rng = np.random.default_rng(int(seed * 1000))
    base = rng.standard_normal(EMBEDDING_DIM).astype("float32")
    base /= np.linalg.norm(base)
    return np.array([base], dtype="float32")


class TestSemanticCache(unittest.TestCase):

    def setUp(self):
        # Route the cache to an isolated temp dir so tests never touch the
        # real cache_faiss.index / cache_metadata.json on disk.
        import tempfile
        self._tmpdir = tempfile.TemporaryDirectory()
        tmp_path = Path(self._tmpdir.name)

        patcher_index = patch("agent.semantic_cache.CACHE_INDEX_PATH", tmp_path / "cache.index")
        patcher_meta = patch("agent.semantic_cache.CACHE_META_PATH", tmp_path / "cache_meta.json")
        patcher_index.start()
        patcher_meta.start()
        self.addCleanup(patcher_index.stop)
        self.addCleanup(patcher_meta.stop)

        self.cache = SemanticCache(threshold=0.88)

    def _add(self, query, answer, vec_seed, tool_used="vector", sources=None):
        with patch.object(self.cache, "_get_embedding", return_value=_vec(vec_seed)):
            self.cache.add(query, answer, tool_used, sources or [])

    def _lookup(self, query, vec_seed):
        with patch.object(self.cache, "_get_embedding", return_value=_vec(vec_seed)):
            return self.cache.lookup(query)

    def test_empty_cache_returns_none(self):
        result = self._lookup("any question", vec_seed=1.0)
        self.assertIsNone(result)

    def test_near_duplicate_query_hits_cache(self):
        self._add("is there a cheap plan under 500", "Yes, several plans...", vec_seed=1.0)
        # Same embedding seed simulates a semantically-identical rephrasing.
        result = self._lookup("any budget recharge below 500 rupees", vec_seed=1.0)
        self.assertIsNotNone(result)
        self.assertEqual(result["answer"], "Yes, several plans...")

    def test_dissimilar_query_misses_cache(self):
        self._add("is there a cheap plan under 500", "Yes, several plans...", vec_seed=1.0)
        result = self._lookup("how do I port my number to Jio", vec_seed=99.0)
        self.assertIsNone(result)

    def test_expired_entry_is_not_returned(self):
        self._add("plan validity question", "Validity is 28 days", vec_seed=2.0)
        # Force the stored entry to look 25 hours old (TTL is 24h).
        self.cache.metadata["0"]["timestamp"] = time.time() - (25 * 3600)
        result = self._lookup("plan validity question", vec_seed=2.0)
        self.assertIsNone(result)

    def test_clear_removes_all_entries(self):
        self._add("question one", "answer one", vec_seed=3.0)
        self._add("question two", "answer two", vec_seed=4.0)
        self.assertEqual(self.cache.index.ntotal, 2)

        self.cache.clear()

        self.assertEqual(self.cache.index.ntotal, 0)
        self.assertEqual(self.cache.metadata, {})
        # And a lookup against a previously-cached query now misses.
        result = self._lookup("question one", vec_seed=3.0)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
