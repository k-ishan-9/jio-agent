"""
api/metrics.py — observability counters for the /ask pipeline: cache hit
rate, guardrail rejection rate, and SQL-vs-vector-vs-hybrid routing
distribution, backed by Redis with an in-process fallback.

Backed by Redis (rather than a purely local Counter) for the same reason
as api/rate_limit.py: with more than one API process, in-memory counters
each show a different partial picture, while a Redis hash gives one true
count shared across every instance. Falls back to an in-process Counter
if Redis is briefly unreachable, so /metrics still returns something
useful instead of erroring.
"""

import threading
import time
from collections import Counter

import redis

from config import REDIS_URL

REDIS_METRICS_KEY = "jio:metrics:counters"

_redis_client = redis.from_url(REDIS_URL, socket_connect_timeout=1, socket_timeout=1)

_lock = threading.Lock()
_counters = Counter()
_start_time = time.time()


def incr(name: str, amount: int = 1):
    try:
        _redis_client.hincrby(REDIS_METRICS_KEY, name, amount)
    except redis.RedisError:
        with _lock:
            _counters[name] += amount


def _read_counts() -> dict:
    try:
        raw = _redis_client.hgetall(REDIS_METRICS_KEY)
        return {k.decode(): int(v) for k, v in raw.items()}
    except redis.RedisError:
        with _lock:
            return dict(_counters)


def snapshot() -> dict:
    c = _read_counts()

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
