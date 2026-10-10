"""Token-bucket rate limiting per tenant.

Redis-backed when REDIS_URL is set and the `redis` package is importable;
otherwise a process-local in-memory bucket. Exceeding the limit raises 429.
"""
from __future__ import annotations

import asyncio
import os
import time

from fastapi import Depends, HTTPException, status

from .auth import Principal, get_principal

_REDIS_CLIENT = None
_REDIS_TODAY_INIT = False


def _redis():
    global _REDIS_CLIENT, _REDIS_TODAY_INIT
    if _REDIS_TODAY_INIT:
        return _REDIS_CLIENT
    _REDIS_TODAY_INIT = True
    url = os.environ.get("REDIS_URL", "").strip()
    if not url:
        return None
    try:
        import redis.asyncio as redis

        _REDIS_CLIENT = redis.from_url(url, decode_responses=True)
    except Exception:
        _REDIS_CLIENT = None
    return _REDIS_CLIENT


class RateLimiter:
    """Fixed-window-ish token bucket. capacity tokens refill over window_s."""

    def __init__(self, capacity: int = 120, window_s: float = 60.0) -> None:
        self.capacity = int(os.environ.get("PAZUZU_RATE_LIMIT_PER_MIN", str(capacity)))
        self.window_s = window_s
        self._buckets: dict[str, tuple[float, float]] = {}  # tenant -> (tokens, last_refill)
        self._lock = asyncio.Lock()

    async def _local_allow(self, tenant: str) -> bool:
        now = time.monotonic()
        async with self._lock:
            tokens, last = self._buckets.get(tenant, (float(self.capacity), now))
            tokens = min(float(self.capacity), tokens + (now - last) * self.capacity / self.window_s)
            if tokens < 1.0:
                self._buckets[tenant] = (tokens, now)
                return False
            self._buckets[tenant] = (tokens - 1.0, now)
            return True

    async def _redis_allow(self, client, tenant: str) -> bool:
        key = f"pazuzu:rl:{tenant}"
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, int(self.window_s))
        return count <= self.capacity

    async def allow(self, tenant: str) -> bool:
        client = _redis()
        if client is not None:
            try:
                return await self._redis_allow(client, tenant)
            except Exception:
                pass  # fall through to local on redis errors
        return await self._local_allow(tenant)


_limiter = RateLimiter()


async def rate_limit_dep(principal: Principal = Depends(get_principal)) -> Principal:
    if not await _limiter.allow(principal.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded for tenant '{principal.tenant_id}'",
            headers={"Retry-After": "60"},
        )
    return principal
