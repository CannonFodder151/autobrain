"""Per-user AI usage caps (AUT-302).

Redis-backed fixed-window counters, shared across backend workers. Two counters
per user: a burst window (per AI_RATE_WINDOW_SECONDS) and a UTC-day total. Both
are enforced as a FastAPI dependency before any 9Router spend happens.

Fail-closed: if Redis is unreachable the limiter returns 503 rather than let
unmetered AI requests through.
"""

import time

from fastapi import Depends, HTTPException
from redis.asyncio import Redis

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.logging import get_logger
from app.models.user import User

logger = get_logger(__name__)

_bump_ttl_multiplier = 2  # counters live past their window so late arrivals still count


def _client() -> Redis:
    return Redis.from_url(settings.REDIS_URL, decode_responses=True)


async def _bump(key: str, ttl: int) -> int:
    """INCR a key (expiring it) and return the new count. Raises on Redis failure."""
    r = _client()
    try:
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, ttl)
        return int((await pipe.execute())[0])
    finally:
        await r.aclose()


async def require_ai_rate_limit(user: User = Depends(get_current_user)) -> User:
    """Reject the request with 429 when the user is over their AI budget.

    Counting here (not per-AI-module) keeps one shared budget per account so a
    user cannot dodge the cap by rotating between features.
    """
    now = int(time.time())
    try:
        burst = await _bump(
            f"ai:burst:{user.id}:{now // settings.AI_RATE_WINDOW_SECONDS}",
            settings.AI_RATE_WINDOW_SECONDS * _bump_ttl_multiplier,
        )
        day = await _bump(
            f"ai:day:{user.id}:{now // 86400}",
            86400 * _bump_ttl_multiplier,
        )
    except Exception as exc:
        logger.warning("ai_rate_limit_unavailable", error=str(exc))
        raise HTTPException(status_code=503, detail="AI rate limiter unavailable") from exc
    if burst > settings.AI_RATE_LIMIT_PER_WINDOW or day > settings.AI_DAILY_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="AI request limit reached. Try again later.",
            headers={"Retry-After": str(settings.AI_RATE_WINDOW_SECONDS)},
        )
    return user
