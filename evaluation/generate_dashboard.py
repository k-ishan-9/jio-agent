"""
evaluation/generate_dashboard.py — renders evaluation/eval_history.jsonl
(written by run_eval.py on every run) into a single self-contained HTML
page: pass rate over time plus the SQL/vector/hybrid routing distribution
for the most recent run. No external chart library — a handful of SVG
elements laid out from the history data, so the file has zero dependencies
and opens directly in a browser.

Usage:
    python evaluation/run_eval.py --base-url http://localhost:8000
    python evaluation/generate_dashboard.py
"""

import json
from pathlib import Path

HISTORY_PATH = Path(__file__).parent / "eval_history.jsonl"
OUTPUT_PATH = Path(__file__).parent / "eval_dashboard.html"


def load_history() -> list:
    if not HISTORY_PATH.exists():
        return []
    entries = []
    with open(HISTORY_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def _pass_rate_svg(history: list, width=760, height=220) -> str:
    if not history:
        return "<p>No evaluation runs yet.</p>"

    pad = 40
    inner_w, inner_h = width - 2 * pad, height - 2 * pad
    n = len(history)
    points = []
    for i, entry in enumerate(history):
        x = pad + (i / max(n - 1, 1)) * inner_w
        y = pad + (1 - entry["pass_rate"]) * inner_h
        points.append((x, y))

    path = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#0054B4">'
        f'<title>{history[i]["passed"]}/{history[i]["total"]} ({history[i]["pass_rate"]:.0%})</title></circle>'
        for i, (x, y) in enumerate(points)
    )
    gridlines = "".join(
        f'<line x1="{pad}" y1="{pad + f * inner_h:.1f}" x2="{width - pad}" y2="{pad + f * inner_h:.1f}" '
        f'stroke="#E5E7EB" stroke-width="1"/>'
        f'<text x="{pad - 8}" y="{pad + f * inner_h + 4:.1f}" font-size="11" fill="#6B7280" text-anchor="end">{int((1 - f) * 100)}%</text>'
        for f in (0, 0.25, 0.5, 0.75, 1.0)
    )

    return f"""
    <svg viewBox="0 0 {width} {height}" width="100%" height="{height}" xmlns="http://www.w3.org/2000/svg">
      {gridlines}
      <path d="{path}" fill="none" stroke="#0054B4" stroke-width="2.5"/>
      {dots}
    </svg>
    """


def _routing_bars_svg(latest: dict, width=400, height=180) -> str:
    counts = latest.get("tool_counts", {})
    labels = [("sql", "#0054B4"), ("vector", "#00A34E"), ("both", "#B4009E"), ("none", "#9CA3AF")]
    max_val = max([counts.get(k, 0) for k, _ in labels] + [1])
    bar_w = 70
    gap = 30
    pad = 40

    bars = ""
    for i, (label, color) in enumerate(labels):
        val = counts.get(label, 0)
        bar_h = (val / max_val) * (height - 2 * pad) if max_val else 0
        x = pad + i * (bar_w + gap)
        y = height - pad - bar_h
        bars += (
            f'<rect x="{x}" y="{y:.1f}" width="{bar_w}" height="{bar_h:.1f}" fill="{color}" rx="4"/>'
            f'<text x="{x + bar_w/2}" y="{height - pad + 16}" font-size="12" fill="#1F2937" text-anchor="middle">{label}</text>'
            f'<text x="{x + bar_w/2}" y="{y - 6:.1f}" font-size="13" fill="#1F2937" text-anchor="middle" font-weight="600">{val}</text>'
        )

    return f"""
    <svg viewBox="0 0 {width} {height}" width="100%" height="{height}" xmlns="http://www.w3.org/2000/svg">
      <line x1="{pad}" y1="{height - pad}" x2="{width - pad}" y2="{height - pad}" stroke="#D1D5DB"/>
      {bars}
    </svg>
    """


def generate():
    history = load_history()
    latest = history[-1] if history else None

    summary_html = ""
    if latest:
        import datetime
        ts = datetime.datetime.fromtimestamp(latest["timestamp"]).strftime("%Y-%m-%d %H:%M")
        summary_html = f"""
        <div class="summary-row">
          <div class="stat"><div class="stat-value">{latest['pass_rate']:.0%}</div><div class="stat-label">Latest pass rate</div></div>
          <div class="stat"><div class="stat-value">{latest['passed']}/{latest['total']}</div><div class="stat-label">Questions passed</div></div>
          <div class="stat"><div class="stat-value">{len(history)}</div><div class="stat-label">Total runs recorded</div></div>
          <div class="stat"><div class="stat-value">{ts}</div><div class="stat-label">Last run</div></div>
        </div>
        """

    html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Jio AI Agent — Evaluation Dashboard</title>
<style>
  body {{ font-family: 'Inter', 'Segoe UI', sans-serif; background: #F5F7FA; color: #1F2937; margin: 0; padding: 32px; }}
  .container {{ max-width: 860px; margin: 0 auto; }}
  h1 {{ font-size: 22px; color: #0A2885; }}
  h2 {{ font-size: 15px; color: #1F2937; margin-top: 32px; }}
  .card {{ background: white; border-radius: 12px; padding: 20px 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); border: 1px solid #E5E7EB; margin-top: 12px; }}
  .summary-row {{ display: flex; gap: 24px; flex-wrap: wrap; }}
  .stat {{ min-width: 140px; }}
  .stat-value {{ font-size: 24px; font-weight: 700; color: #0054B4; }}
  .stat-label {{ font-size: 12px; color: #6B7280; margin-top: 2px; }}
  p {{ color: #6B7280; font-size: 13px; }}
</style>
</head>
<body>
<div class="container">
  <h1>Jio AI Agent — Evaluation Dashboard</h1>
  <p>Generated from evaluation/eval_history.jsonl — a "pass" means the agent produced a non-empty, tool-grounded answer (called find_jio_plans or search_jio_faq_and_info) rather than guessing or erroring out.</p>

  {summary_html}

  <h2>Pass rate over time</h2>
  <div class="card">{_pass_rate_svg(history)}</div>

  <h2>Retrieval routing distribution (latest run)</h2>
  <div class="card">{_routing_bars_svg(latest) if latest else '<p>No runs yet.</p>'}</div>
</div>
</body>
</html>
"""
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"Dashboard written to {OUTPUT_PATH}")


if __name__ == "__main__":
    generate()
