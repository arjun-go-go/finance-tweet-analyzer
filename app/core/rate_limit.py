"""Redis-backed fixed-window limits for authentication endpoints."""

import redis
from fastapi import HTTPException, Request, status
from loguru import logger

from app.core.config import settings

_redis_client: redis.Redis | None = None

_INCREMENT_WITH_TTL = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""


def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


def allow_request(key: str, *, limit: int, window: int) -> bool:
    """Return whether a request fits inside the current Redis window."""
    try:
        count = int(
            _get_redis().eval(
                _INCREMENT_WITH_TTL,
                1,
                f"rate:{key}",
                window,
            )
        )
    except redis.RedisError as exc:
        logger.error("Authentication rate limiter unavailable: {}", exc)
        return False
    return count <= limit


def enforce_auth_rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    route_key = request.url.path.rsplit("/", 1)[-1]
    if not allow_request(
        f"auth:{route_key}:{client_ip}",
        limit=settings.auth_rate_limit_attempts,
        window=settings.auth_rate_limit_window_seconds,
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication attempts",
        )
