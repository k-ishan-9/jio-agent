"""
tests/test_logging_utils.py — unit tests for PII scrubbing and the JSON
log formatter (api/logging_utils.py).
"""

import json
import logging
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.logging_utils import JsonFormatter, scrub_pii


class TestScrubPii(unittest.TestCase):

    def test_redacts_email(self):
        result = scrub_pii("contact me at kishan@example.com please")
        self.assertNotIn("kishan@example.com", result)
        self.assertIn("[EMAIL_REDACTED]", result)

    def test_redacts_indian_mobile_number(self):
        result = scrub_pii("my number is 9876543210, call me")
        self.assertNotIn("9876543210", result)
        self.assertIn("[PHONE_REDACTED]", result)

    def test_redacts_long_digit_sequences_like_account_numbers(self):
        result = scrub_pii("my account number is 1234567890123")
        self.assertNotIn("1234567890123", result)
        self.assertIn("[NUMBER_REDACTED]", result)

    def test_leaves_ordinary_text_untouched(self):
        text = "what is the cheapest plan under 500 rupees with netflix"
        self.assertEqual(scrub_pii(text), text)

    def test_handles_empty_string(self):
        self.assertEqual(scrub_pii(""), "")


class TestJsonFormatter(unittest.TestCase):

    def test_formats_log_record_as_valid_json(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test_logger", level=logging.INFO, pathname=__file__,
            lineno=1, msg="hello %s", args=("world",), exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        self.assertEqual(parsed["message"], "hello world")
        self.assertEqual(parsed["level"], "INFO")
        self.assertEqual(parsed["logger"], "test_logger")
        self.assertIn("timestamp", parsed)

    def test_includes_exception_info_when_present(self):
        formatter = JsonFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            record = logging.LogRecord(
                name="test_logger", level=logging.ERROR, pathname=__file__,
                lineno=1, msg="failed", args=(), exc_info=sys.exc_info(),
            )
        output = formatter.format(record)
        parsed = json.loads(output)
        self.assertIn("exception", parsed)
        self.assertIn("ValueError: boom", parsed["exception"])


if __name__ == "__main__":
    unittest.main()
