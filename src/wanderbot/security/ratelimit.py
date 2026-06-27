"""Per-user / per-IP rate limiting.

Redis-backed fixed-window limiter in production (shared across replicas); falls
back to an in-process counter when Redis is unavailable so local dev still works.
"""

from __future__ import annotations

import time

from wanderbot.config import Settings, get_settings
from wanderbot.observability.logging import get_logger

log = get_logger(__name__)


class RateLimiter:
    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self._redis = None
        self._local: dict[str, tuple[int, float]] = {}

    async def _get_redis(self):  # noqa: ANN202
        if self._redis is None:
            try:
                import redis.asyncio as aioredis

                self._redis = aioredis.from_url(self._settings.redis_url)
                await self._redis.ping()
            except Exception as exc:  # pragma: no cover - fallback path
                log.warning("redis_unavailable_local_fallback", error=str(exc))
                self._redis = False  # sentinel: don't retry
        return self._redis or None

    async def allow(self, key: str, *, limit: int = 30, window_s: int = 60) -> bool:
        redis = await self._get_redis()
        if redis is not None:
            bucket = f"rl:{key}:{int(time.time() // window_s)}"
            count = await redis.incr(bucket)
            if count == 1:
                await redis.expire(bucket, window_s)
            return count <= limit

        # In-process fixed window.
        now = time.time()
        window = int(now // window_s)
        count, w = self._local.get(key, (0, window))
        if w != window:
            count, w = 0, window
        count += 1
        self._local[key] = (count, w)
        return count <= limit
