"""
tests/test_rate_limit.py — unit tests for the in-process sliding-window
rate limiter (api/rate_limit.py) that protects POST /ask from scripted
bursts.
"""

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import HTTPException

from api import rate_limit


def _fake_request(ip="1.2.3.4"):
    req = MagicMock()
    req.headers = {}
    req.client.host = ip
    return req


class TestRateLimit(unittest.TestCase):

    def setUp(self):
        rate_limit._hits.clear()
        self._orig_window = rate_limit.WINDOW_SECONDS
        self._orig_max = rate_limit.MAX_REQUESTS_PER_WINDOW
        rate_limit.WINDOW_SECONDS = 60
        rate_limit.MAX_REQUESTS_PER_WINDOW = 3

    def tearDown(self):
        rate_limit.WINDOW_SECONDS = self._orig_window
        rate_limit.MAX_REQUESTS_PER_WINDOW = self._orig_max
        rate_limit._hits.clear()

    def test_allows_requests_under_the_limit(self):
        req = _fake_request()
        for _ in range(3):
            asyncio.run(rate_limit.enforce_rate_limit(req))  # should not raise

    def test_blocks_requests_over_the_limit(self):
        req = _fake_request()
        for _ in range(3):
            asyncio.run(rate_limit.enforce_rate_limit(req))
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(rate_limit.enforce_rate_limit(req))
        self.assertEqual(ctx.exception.status_code, 429)

    def test_different_clients_have_independent_limits(self):
        req_a = _fake_request(ip="1.1.1.1")
        req_b = _fake_request(ip="2.2.2.2")
        for _ in range(3):
            asyncio.run(rate_limit.enforce_rate_limit(req_a))
        # Client B should be unaffected by client A's usage.
        asyncio.run(rate_limit.enforce_rate_limit(req_b))

    def test_x_forwarded_for_header_used_when_present(self):
        req = _fake_request(ip="10.0.0.1")
        req.headers = {"x-forwarded-for": "9.9.9.9, 10.0.0.1"}
        key = rate_limit._client_key(req)
        self.assertEqual(key, "9.9.9.9")


if __name__ == "__main__":
    unittest.main()
