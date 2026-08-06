"""
evaluation/run_eval.py — test question set, hitting a live API instance.

Usage:
    python evaluation/run_eval.py --base-url http://localhost:8000
"""

import argparse
import json
from pathlib import Path

import requests

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

    Path(output_path).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved {len(results)} results to: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--output", default="evaluation_results.json")
    args = parser.parse_args()
    run(args.base_url, args.output)
