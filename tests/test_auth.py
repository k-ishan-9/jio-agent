"""
tests/test_auth.py — unit tests for the optional API-key dependency
(api/auth.py) used on POST /ask.
"""

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import HTTPException

from api import auth


class TestRequireApiKey(unittest.TestCase):

    @patch("api.auth.API_KEY", "")
    def test_no_key_configured_allows_any_request(self):
        asyncio.run(auth.require_api_key(x_api_key=""))  # should not raise
        asyncio.run(auth.require_api_key(x_api_key="anything"))  # should not raise

    @patch("api.auth.API_KEY", "super-secret")
    def test_correct_key_is_allowed(self):
        asyncio.run(auth.require_api_key(x_api_key="super-secret"))  # should not raise

    @patch("api.auth.API_KEY", "super-secret")
    def test_missing_key_is_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(auth.require_api_key(x_api_key=""))
        self.assertEqual(ctx.exception.status_code, 401)

    @patch("api.auth.API_KEY", "super-secret")
    def test_wrong_key_is_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(auth.require_api_key(x_api_key="wrong-key"))
        self.assertEqual(ctx.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
