"""
tests/test_ask_stream.py — integration test for the SSE /ask/stream
endpoint. The cache/guardrail/agent pipeline is mocked so this runs
offline: it verifies the endpoint frames the already-generated answer as
a sequence of "chunk" SSE events followed by one "done" event carrying
sources/tool_used/session_id, which is what static/widget.js parses.
"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

import api.main as main_module


def _parse_sse(raw_text: str):
    """Parse 'event: X\\ndata: Y\\n\\n' frames into a list of (event, data) tuples."""
    frames = [f for f in raw_text.split("\n\n") if f.strip()]
    parsed = []
    for frame in frames:
        event_line = next(l for l in frame.splitlines() if l.startswith("event: "))
        data_line = next(l for l in frame.splitlines() if l.startswith("data: "))
        parsed.append((event_line[len("event: "):], json.loads(data_line[len("data: "):])))
    return parsed


class TestAskStream(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(main_module.app)

    @patch("api.main.semantic_cache")
    @patch("api.main.evaluate_intent", return_value=(True, ""))
    @patch("api.main.rewrite_query", side_effect=lambda q: q)
    @patch("api.main.run_agent_query", new_callable=AsyncMock)
    def test_stream_emits_chunks_then_done(self, mock_run_agent, mock_rewrite, mock_evaluate, mock_cache):
        mock_cache.lookup.return_value = None
        mock_run_agent.return_value = main_module.AskResponse(
            answer="Jio plan 479 includes Netflix",
            sources=[main_module.SourceItem(title="Plan 479", url="http://x/479", score=0.93)],
            tool_used="vector",
            session_id="test-session",
        )

        resp = self.client.post("/ask/stream", json={"question": "does 479 have netflix"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/event-stream", resp.headers["content-type"])

        events = _parse_sse(resp.text)
        chunk_events = [e for e in events if e[0] == "chunk"]
        done_events = [e for e in events if e[0] == "done"]

        self.assertTrue(len(chunk_events) >= 1)
        self.assertEqual(len(done_events), 1)

        reconstructed = "".join(e[1]["text"] for e in chunk_events)
        self.assertEqual(reconstructed, "Jio plan 479 includes Netflix")

        done_data = done_events[0][1]
        self.assertEqual(done_data["tool_used"], "vector")
        self.assertEqual(done_data["session_id"], "test-session")
        self.assertEqual(done_data["sources"][0]["score"], 0.93)

    @patch("api.main.semantic_cache")
    def test_stream_uses_cache_hit_without_calling_agent(self, mock_cache):
        mock_cache.lookup.return_value = {
            "answer": "Cached answer here",
            "tool_used": "sql",
            "sources": [],
        }
        with patch("api.main.run_agent_query", new_callable=AsyncMock) as mock_run_agent:
            resp = self.client.post("/ask/stream", json={"question": "any cached question"})
            mock_run_agent.assert_not_called()

        events = _parse_sse(resp.text)
        reconstructed = "".join(e[1]["text"] for e in events if e[0] == "chunk")
        self.assertEqual(reconstructed, "Cached answer here")


if __name__ == "__main__":
    unittest.main()
