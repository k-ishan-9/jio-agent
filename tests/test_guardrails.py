"""
tests/test_guardrails.py — unit tests for the off-topic guardrail and query
rewriting logic (agent/guardrails.py). The Gemini client is mocked so these
tests run offline and deterministically instead of depending on live model
output.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent import guardrails


def _fake_client(response_text: str) -> MagicMock:
    client = MagicMock()
    client.models.generate_content.return_value = MagicMock(text=response_text)
    return client


class TestEvaluateIntent(unittest.TestCase):

    @patch("agent.guardrails.retrieval_tools.get_client")
    def test_on_topic_query_is_safe(self, mock_get_client):
        mock_get_client.return_value = _fake_client("SAFE")
        is_safe, refusal = guardrails.evaluate_intent("What are Jio's postpaid plans under 500?")
        self.assertTrue(is_safe)
        self.assertEqual(refusal, "")

    @patch("agent.guardrails.retrieval_tools.get_client")
    def test_off_topic_query_is_blocked(self, mock_get_client):
        mock_get_client.return_value = _fake_client("BLOCK")
        is_safe, refusal = guardrails.evaluate_intent("Write me a Python quicksort implementation")
        self.assertFalse(is_safe)
        self.assertIn("Jio", refusal)

    @patch("agent.guardrails.retrieval_tools.get_client")
    def test_competitor_comparison_is_blocked(self, mock_get_client):
        mock_get_client.return_value = _fake_client("BLOCK")
        is_safe, refusal = guardrails.evaluate_intent("Is Airtel cheaper than Jio?")
        self.assertFalse(is_safe)

    @patch("agent.guardrails.retrieval_tools.get_client")
    def test_history_context_is_passed_to_prompt(self, mock_get_client):
        client = _fake_client("SAFE")
        mock_get_client.return_value = client
        history = [
            {"role": "user", "content": "What are Jio prepaid plans?"},
            {"role": "model", "content": "Here are a few options..."},
        ]
        is_safe, _ = guardrails.evaluate_intent("what about postpaid?", history_context=history)
        self.assertTrue(is_safe)
        prompt_used = client.models.generate_content.call_args.kwargs["contents"]
        self.assertIn("Jio prepaid plans", prompt_used)
        self.assertIn("what about postpaid?", prompt_used)

    @patch("agent.guardrails.retrieval_tools.get_client")
    def test_fails_open_when_model_errors(self, mock_get_client):
        """If the guardrail model call itself fails, the request should be
        allowed through rather than the whole pipeline breaking."""
        mock_get_client.side_effect = RuntimeError("Gemini API unavailable")
        is_safe, refusal = guardrails.evaluate_intent("What are Jio's plans?")
        self.assertTrue(is_safe)
        self.assertEqual(refusal, "")


class TestRewriteQuery(unittest.TestCase):

    @patch("agent.guardrails.retrieval_tools.get_client")
    def test_rewrites_casual_query(self, mock_get_client):
        mock_get_client.return_value = _fake_client("Jio mobile plans under 500 Netflix")
        result = guardrails.rewrite_query(
            "hey is there any cheap mobile plans under 500 rupees that give netflix"
        )
        self.assertEqual(result, "Jio mobile plans under 500 Netflix")

    @patch("agent.guardrails.retrieval_tools.get_client")
    def test_falls_back_to_original_on_error(self, mock_get_client):
        mock_get_client.side_effect = RuntimeError("Gemini API unavailable")
        original = "how do i set up jio airfiber"
        result = guardrails.rewrite_query(original)
        self.assertEqual(result, original)

    @patch("agent.guardrails.retrieval_tools.get_client")
    def test_falls_back_to_original_on_empty_response(self, mock_get_client):
        mock_get_client.return_value = _fake_client("")
        original = "does the 1549 plan include netflix"
        result = guardrails.rewrite_query(original)
        self.assertEqual(result, original)


if __name__ == "__main__":
    unittest.main()
