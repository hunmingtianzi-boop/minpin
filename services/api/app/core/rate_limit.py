from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis
from redis.exceptions import RedisError

_FIXED_WINDOW_LUA = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {current, ttl}
"""


class RateLimitBackendUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int


class RedisRateLimiter:
    """Accountable, multi-instance public chat limiter.

    AI calls fail closed when Redis is unavailable. The public card itself remains
    independent and can continue serving static content.
    """

    def __init__(self, redis: Redis, *, prefix: str = "cf:ratelimit") -> None:
        self._redis = redis
        self._prefix = prefix

    async def check(
        self, *, bucket: str, subject: str, limit: int, window_seconds: int
    ) -> RateLimitDecision:
        key = f"{self._prefix}:{bucket}:{subject}"
        try:
            current, ttl = await self._redis.eval(
                _FIXED_WINDOW_LUA,
                1,
                key,
                window_seconds,
            )
        except RedisError as exc:
            raise RateLimitBackendUnavailable("rate limiter unavailable") from exc

        used = int(current)
        retry_after = max(int(ttl), 1)
        return RateLimitDecision(
            allowed=used <= limit,
            limit=limit,
            remaining=max(limit - used, 0),
            retry_after_seconds=retry_after,
        )
