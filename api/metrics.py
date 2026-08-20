"""
api/metrics.py — in-process observability counters for the /ask pipeline.

Tracks cache hit rate, guardrail rejection rate, and SQL-vs-vector-vs-hybrid
routing distribution so these architectural decisions are measurable rather
than just asserted. Deliberately dependency-free (no prometheus_client) —
a single process-local counter dict is enough for a single-instance
deployment and keeps the report/demo story simple.
"""

import threading
import time
from collections import Counter

_lock = threading.Lock()
_counters = Counter()
_start_time = time.time()


def incr(name: str, amount: int = 1):
    with _lock:
        _counters[name] += amount


def snapshot() -> dict:
    with _lock:
        c = dict(_counters)

    total_requests = c.get("requests_total", 0)
    cache_hits = c.get("cache_hit", 0)
    cache_misses = c.get("cache_miss", 0)
    cache_lookups = cache_hits + cache_misses
    guardrail_blocked = c.get("guardrail_blocked", 0)
    guardrail_allowed = c.get("guardrail_allowed", 0)
    guardrail_evaluated = guardrail_blocked + guardrail_allowed

    tool_sql = c.get("tool_sql", 0)
    tool_vector = c.get("tool_vector", 0)
    tool_both = c.get("tool_both", 0)
    tool_none = c.get("tool_none", 0)

    return {
        "uptime_seconds": round(time.time() - _start_time, 1),
        "requests_total": total_requests,
        "cache": {
            "hits": cache_hits,
            "misses": cache_misses,
            "hit_rate": round(cache_hits / cache_lookups, 4) if cache_lookups else None,
        },
        "guardrail": {
            "blocked": guardrail_blocked,
            "allowed": guardrail_allowed,
            "block_rate": round(guardrail_blocked / guardrail_evaluated, 4) if guardrail_evaluated else None,
        },
        "routing": {
            "sql": tool_sql,
            "vector": tool_vector,
            "both": tool_both,
            "none": tool_none,
        },
        "rate_limit": {
            "rejected": c.get("rate_limited", 0),
        },
        "errors": c.get("errors", 0),
    }
