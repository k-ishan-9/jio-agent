"""
api/rate_limit.py — per-IP sliding-ish (fixed-window) rate limiter for
POST /ask, backed by Redis with an automatic in-process fallback.

Why Redis: the project already runs Redis for Celery, and a purely
in-memory limiter only works correctly for a single API process — the
moment you run two instances behind a load balancer, each has its own
counters and a client can get 2x (or Nx) the intended limit by hitting
different instances. Redis gives every instance a shared view.

Why fall back instead of hard-failing: if Redis is briefly unreachable,
rate limiting degrading to a per-process limit (rather than the whole
/ask endpoint going down) is the safer failure mode for a customer
support bot.
"""

import os
import threading
import time
from collections import defaultdict, deque

import redis
from fastapi import HTTPException, Request

from api import metrics, redis_breaker
from config import REDIS_URL

_BREAKER_KEY = "rate_limit"

WINDOW_SECONDS = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))
MAX_REQUESTS_PER_WINDOW = int(os.environ.get("RATE_LIMIT_MAX_REQUESTS", "20"))

_redis_client = redis.from_url(REDIS_URL, socket_connect_timeout=1, socket_timeout=1)

# In-memory fallback (used only when Redis is unreachable)
_lock = threading.Lock()
_hits: dict[str, deque] = defaultdict(deque)


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_redis(key: str) -> bool:
    """Fixed-window counter in Redis. Returns True if the request is allowed."""
    bucket = int(time.time() // WINDOW_SECONDS)
    redis_key = f"ratelimit:{key}:{bucket}"
    count = _redis_client.incr(redis_key)
    if count == 1:
        _redis_client.expire(redis_key, WINDOW_SECONDS)
    return count <= MAX_REQUESTS_PER_WINDOW


def _check_in_memory(key: str) -> bool:
    now = time.time()
    with _lock:
        window = _hits[key]
        while window and now - window[0] > WINDOW_SECONDS:
            window.popleft()
        if len(window) >= MAX_REQUESTS_PER_WINDOW:
            return False
        window.append(now)
        return True


async def enforce_rate_limit(request: Request):
    """FastAPI dependency: raises 429 if the caller has exceeded the window."""
    key = _client_key(request)

    if redis_breaker.is_open(_BREAKER_KEY):
        allowed = _check_in_memory(key)
    else:
        try:
            allowed = _check_redis(key)
            redis_breaker.record_success(_BREAKER_KEY)
        except redis.RedisError:
            redis_breaker.record_failure(_BREAKER_KEY)
            allowed = _check_in_memory(key)

    if not allowed:
        metrics.incr("rate_limited")
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in under {WINDOW_SECONDS}s.",
            headers={"Retry-After": str(WINDOW_SECONDS)},
        )
