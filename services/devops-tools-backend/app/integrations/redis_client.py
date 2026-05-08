"""
Async Redis client wrapper for the portal health cache.

Graceful degradation: if Redis is unreachable we fall through to a
thread-safe in-memory dict, logging the fallback exactly once at WARNING.
Call-sites never need to branch — they always get a `HealthCache` that
either hits Redis or the local dict.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import redis.asyncio as redis_async
from redis.exceptions import RedisError

log = logging.getLogger(__name__)


class HealthCache:
    """Redis-backed cache with in-memory fallback.

    Keys:
        portal:health:{tool_id}   -> JSON HealthStatus (TTL: health_cache_ttl_seconds)
        portal:health:all         -> JSON {tool_id: HealthStatus}
    """

    def __init__(
        self,
        redis_url: str,
        default_ttl_seconds: int = 60,
    ) -> None:
        self._redis_url = redis_url
        self._default_ttl = default_ttl_seconds
        self._client: redis_async.Redis | None = None
        self._mem: dict[str, tuple[float, str]] = {}  # key -> (expires_at, value)
        self._mem_lock = asyncio.Lock()
        self._fallback_logged = False

    async def connect(self) -> None:
        """Open the Redis connection. Safe to call repeatedly."""
        if self._client is not None:
            return
        try:
            self._client = redis_async.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
            )
            # verify
            await self._client.ping()
            log.info("Redis health cache connected at %s", self._redis_url)
        except (RedisError, OSError) as exc:
            self._client = None
            self._log_fallback(f"connect failed: {exc}")

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:  # noqa: BLE001
                pass
            finally:
                self._client = None

    def _log_fallback(self, reason: str) -> None:
        if not self._fallback_logged:
            log.warning(
                "HealthCache falling back to in-memory dict (reason=%s). "
                "Portal health will not be shared across replicas.",
                reason,
            )
            self._fallback_logged = True

    async def set_json(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        payload = json.dumps(value, default=str)

        if self._client is not None:
            try:
                await self._client.set(key, payload, ex=ttl)
                return
            except (RedisError, OSError) as exc:
                self._log_fallback(f"set failed: {exc}")
                self._client = None  # give up on redis for this run

        async with self._mem_lock:
            self._mem[key] = (time.monotonic() + ttl, payload)

    async def get_json(self, key: str) -> Any | None:
        if self._client is not None:
            try:
                raw = await self._client.get(key)
                if raw is None:
                    return None
                return json.loads(raw)
            except (RedisError, OSError) as exc:
                self._log_fallback(f"get failed: {exc}")
                self._client = None

        async with self._mem_lock:
            entry = self._mem.get(key)
            if entry is None:
                return None
            expires_at, payload = entry
            if expires_at < time.monotonic():
                self._mem.pop(key, None)
                return None
            return json.loads(payload)

    async def delete(self, key: str) -> None:
        if self._client is not None:
            try:
                await self._client.delete(key)
                return
            except (RedisError, OSError) as exc:
                self._log_fallback(f"delete failed: {exc}")
                self._client = None

        async with self._mem_lock:
            self._mem.pop(key, None)

    @property
    def backend(self) -> str:
        return "redis" if self._client is not None else "memory"
