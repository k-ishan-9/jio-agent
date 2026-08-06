"""
tests/test_celery_pipeline.py — Verification tests for Celery background tasks and hot reloading.
"""

import sys
import unittest
from pathlib import Path

# Add parent dir to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tasks.celery_app import app
from tasks.scrapers import fetch_plans_signature, fetch_faq_signature
from tasks.pipeline import check_plan_changes, check_faq_changes
from retrieval.tools import setup as setup_tools, reload_faiss_index


class TestCeleryPipeline(unittest.TestCase):

    def setUp(self):
        app.conf.task_always_eager = True
        app.conf.task_eager_propagates = True

    def test_signatures(self):
        plan_sig = fetch_plans_signature()
        faq_sig = fetch_faq_signature()
        self.assertIsInstance(plan_sig, str)
        self.assertIsInstance(faq_sig, str)
        print(f"Plan signature: {plan_sig[:12]}...")
        print(f"FAQ signature: {faq_sig[:12]}...")

    def test_tasks_eager_execution(self):
        plan_res = check_plan_changes.apply()
        self.assertIn("status", plan_res.result)
        print("check_plan_changes eager result:", plan_res.result)

        faq_res = check_faq_changes.apply()
        self.assertIn("status", faq_res.result)
        print("check_faq_changes eager result:", faq_res.result)

    def test_reload_faiss_index(self):
        try:
            setup_tools()
        except FileNotFoundError:
            print("FAISS index files not present yet, testing reload fallback.")
        success = reload_faiss_index()
        print("reload_faiss_index result:", success)


if __name__ == "__main__":
    unittest.main()
