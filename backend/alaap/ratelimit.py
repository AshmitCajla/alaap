"""Fixed-window rate limits per key (usually client IP). Redis when configured, else in-process.

Every customer message spends LLM and speech credits, so public endpoints are limited."""

import threading
import time

from fastapi import HTTPException, Request

from . import config

_lock = threading.Lock()
_counts: dict[str, tuple[int, int]] = {}
_redis = None


def _r():
    global _redis
    if _redis is None and config.REDIS_URL:
        import redis

        _redis = redis.Redis.from_url(config.REDIS_URL)
    return _redis


def hit(key: str, limit: int, window: int = 60) -> bool:
    """Count one request; False when the key is over its limit for this window."""
    if limit <= 0:
        return True
    bucket = int(time.time() // window)
    r = _r()
    if r is not None:
        k = f"alaap:rl:{key}:{bucket}"
        n = r.incr(k)
        if n == 1:
            r.expire(k, window + 5)
        return n <= limit
    with _lock:
        b, n = _counts.get(key, (bucket, 0))
        n = n + 1 if b == bucket else 1
        _counts[key] = (bucket, n)
        if len(_counts) > 50_000:  # keep memory bounded
            for k in [k for k, (bb, _) in _counts.items() if bb != bucket]:
                _counts.pop(k, None)
        return n <= limit


def client_ip(request) -> str:
    # Behind Caddy, uvicorn runs with --proxy-headers so request.client is the real caller.
    return (request.client.host if request.client else "unknown") or "unknown"


def limit(request: Request, name: str, per_min: int) -> None:
    if not hit(f"{name}:{client_ip(request)}", per_min):
        raise HTTPException(429, "Too many requests. Please wait a minute and try again.")
