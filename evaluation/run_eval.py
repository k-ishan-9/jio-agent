"""
evaluation/run_eval.py — test question set, hitting a live API instance.

Usage:
    python evaluation/run_eval.py --base-url http://localhost:8000

Each run is scored and appended to evaluation/eval_history.jsonl, so
evaluation/generate_dashboard.py can chart pass rate over time instead of
each run being a one-off artifact nobody looks at again.
"""

import argparse
import json
import time
from pathlib import Path

import requests

HISTORY_PATH = Path(__file__).parent / "eval_history.jsonl"

TEST_QUESTIONS = [
    "What's the cheapest prepaid plan with 5G?",
    "Show me postpaid plans under Rs.500 with Netflix",
    "What is the most expensive prepaid plan?",
    "Which prepaid plans include Amazon Prime?",
    "What's the cheapest plan with at least 2GB per day data?",
    "Show me all annual prepaid plans",
    "Which postpaid plans support family add-on connections?",
    "What's the cheapest international roaming plan?",
    "What's the cheapest JioFiber plan?",
    "Show me fiber plans with speed above 200 Mbps",
    "What's the cheapest AirFiber plan?",
    "Which fiber plans include Netflix and Amazon Prime both?",
    "What is the price of the fastest fiber plan?",
    "Show me JioFiber prepaid plans",
    "Show me AirFiber special offer plans",
    "How do I port my number to Jio?",
    "How can I activate call forwarding?",
    "What documents do I need to port my number?",
    "How do I check my Jio data balance?",
    "Can I use Jio SIM while traveling internationally?",
    "What is JioAICloud?",
    "What cloud services does Jio offer for businesses?",
    "Tell me about Jio's IoT solutions",
    "What can I do with the MyJio app?",
    "What features does JioHealth app have?",
    "What is 5G and is it available on Jio?",
]


def _is_pass(result: dict) -> bool:
    """A question 'passes' if the agent produced a non-empty, tool-grounded
    answer — i.e. it actually called find_jio_plans or
    search_jio_faq_and_info rather than guessing, and didn't error out.
    There's no ground-truth answer key here, so this checks the project's
    core design guarantee (always grounded, never guessed) rather than
    exact-match correctness."""
    if result.get("tool_used") in (None, "ERROR", "none", "unknown"):
        return False
    answer = result.get("answer") or ""
    return bool(answer.strip()) and "Error:" not in answer


def run(base_url: str, output_path: str):
    results = []
    for i, question in enumerate(TEST_QUESTIONS):
        print(f"[{i+1}/{len(TEST_QUESTIONS)}] {question}")
        try:
            resp = requests.post(f"{base_url}/ask", json={"question": question}, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            results.append({
                "question": question,
                "answer": data["answer"],
                "tool_used": data["tool_used"],
                "sources": data["sources"],
            })
            print(f"    -> tool_used={data['tool_used']}")
        except Exception as e:
            results.append({"question": question, "answer": None, "tool_used": "ERROR", "error": str(e)})
            print(f"    -> ERROR: {e}")

    for r in results:
        r["passed"] = _is_pass(r)

    Path(output_path).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved {len(results)} results to: {output_path}")

    _append_history(results)


def _append_history(results: list):
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    tool_counts = {"sql": 0, "vector": 0, "both": 0, "none": 0, "unknown": 0, "ERROR": 0}
    for r in results:
        tool_counts[r.get("tool_used", "unknown")] = tool_counts.get(r.get("tool_used", "unknown"), 0) + 1

    entry = {
        "timestamp": time.time(),
        "total": total,
        "passed": passed,
        "pass_rate": round(passed / total, 4) if total else 0,
        "tool_counts": tool_counts,
    }
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"Pass rate: {passed}/{total} ({entry['pass_rate']:.0%}). Appended to {HISTORY_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--output", default="evaluation_results.json")
    args = parser.parse_args()
    run(args.base_url, args.output)
