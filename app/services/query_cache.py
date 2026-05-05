"""
Optional Redis-backed JSON cache with in-process fallback (no extra infra required for dev).
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Optional

from app.core.config import settings

_redis = None
_memory: dict[str, tuple[float, str]] = {}
_mem_lock = asyncio.Lock()


def _now() -> float:
    return time.monotonic()


async def _get_redis():
    global _redis
    if _redis is not None:
        return _redis
    if not settings.REDIS_URL:
        return None
    try:
        import redis.asyncio as redis_lib

        _redis = redis_lib.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
        return _redis
    except Exception:
        return None


async def cache_get_json(key: str) -> Optional[Any]:
    r = await _get_redis()
    if r:
        raw = await r.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    async with _mem_lock:
        hit = _memory.get(key)
        if not hit:
            return None
        exp, payload = hit
        if exp < _now():
            del _memory[key]
            return None
        return json.loads(payload)


async def cache_set_json(key: str, value: Any, ttl_seconds: int) -> None:
    r = await _get_redis()
    payload = json.dumps(value, separators=(",", ":"), default=str)
    if r:
        await r.set(key, payload, ex=ttl_seconds)
        return

    async with _mem_lock:
        # Cap memory cache size (simple eviction)
        if len(_memory) > 2000:
            _memory.clear()
        _memory[key] = (_now() + ttl_seconds, payload)


async def invalidate_profiles_cache() -> None:
    """Clear all profile list/search entries."""
    r = await _get_redis()
    prefix = "insighta:profiles:"
    if r:
        async for key in r.scan_iter(f"{prefix}*"):
            await r.delete(key)
        return

    async with _mem_lock:
        for k in list(_memory.keys()):
            if k.startswith(prefix):
                del _memory[k]
