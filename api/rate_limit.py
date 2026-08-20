"""
api/rate_limit.py — simple in-process sliding-window rate limiter.

Protects POST /ask from scripted bursts that would otherwise rack up Gemini
API cost with no limit. Deliberately dependency-free (no slowapi/redis) —
an in-memory per-IP window is enough for a single-instance deployment; a
multi-instance deployment would need a shared store (e.g. Redis, which the
project already runs for Celery) instead.
"""

import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from api import metrics

WINDOW_SECONDS = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))
MAX_REQUESTS_PER_WINDOW = int(os.environ.get("RATE_LIMIT_MAX_REQUESTS", "20"))

_lock = threading.Lock()
_hits: dict[str, deque] = defaultdict(deque)


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def enforce_rate_limit(request: Request):
    """FastAPI dependency: raises 429 if the caller has exceeded the window."""
    key = _client_key(request)
    now = time.time()

    with _lock:
        window = _hits[key]
        while window and now - window[0] > WINDOW_SECONDS:
            window.popleft()

        if len(window) >= MAX_REQUESTS_PER_WINDOW:
            metrics.incr("rate_limited")
            retry_after = max(1, int(WINDOW_SECONDS - (now - window[0])))
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Try again in {retry_after}s.",
                headers={"Retry-After": str(retry_after)},
            )

        window.append(now)
