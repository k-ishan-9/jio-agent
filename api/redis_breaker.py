"""
api/redis_breaker.py — tiny circuit breaker shared by api/rate_limit.py
and api/metrics.py.

Without this, every single request pays the full Redis connect timeout
(on a deployment with no Redis at all — e.g. the lean single-process
Render build) before falling back to the in-process path, adding real
latency to every request. This remembers a recent failure and skips
straight to the fallback for a cooldown window instead of retrying a
connection that's very likely still down.
"""

import time

COOLDOWN_SECONDS = 30

_last_failure_at: dict[str, float] = {}


def is_open(breaker_key: str) -> bool:
    """True if this breaker is in its cooldown window (skip Redis, use fallback)."""
    last_failure = _last_failure_at.get(breaker_key)
    return last_failure is not None and (time.time() - last_failure) < COOLDOWN_SECONDS


def record_failure(breaker_key: str):
    _last_failure_at[breaker_key] = time.time()


def record_success(breaker_key: str):
    _last_failure_at.pop(breaker_key, None)
