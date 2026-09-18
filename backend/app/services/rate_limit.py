"""Per-user rate limiting (AUT-302, AUT-1607).

Redis-backed fixed-window counters, shared across backend workers.

AI limiter (fail-closed): two counters per user — burst (per AI_RATE_WINDOW_SECONDS)
and UTC-day total. Enforced before any 9Router spend.

Rego limiter (fail-open): single UTC-hour counter per user. Logs a warning on
Redis failure but allows the request through — rego lookup is not cost-critical
enough to block users when Redis is down.

Pure logic only — FastAPI DI wrappers live in ``api.rate_deps``.
"""

import time

from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

AI_RATE_BUMP_TTL_MULTIPLIER = 2  # counters live past their window so late arrivals still count

_BUMP_TTL_MULTIPLIER = 2  # counters live past their window so late arrivals still count


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


async def _bump_ai(user_id: int) -> tuple[int, int]:
    """Bump both the AI burst counter and UTC-day counter for a user.

    Returns (burst_count, day_count). Raises on Redis failure — the caller
    decides whether to fail-closed (503) or fail-open (proceed).
    """
    now = int(time.time())
    burst = await _bump(
        f"ai:burst:{user_id}:{now // settings.AI_RATE_WINDOW_SECONDS}",
        settings.AI_RATE_WINDOW_SECONDS * AI_RATE_BUMP_TTL_MULTIPLIER,
    )
    day = await _bump(
        f"ai:day:{user_id}:{now // 86400}",
        86400 * AI_RATE_BUMP_TTL_MULTIPLIER,
    )
    return burst, day


async def _bump_rego(user_id: int) -> tuple[int, int]:
    """Bump the rego rate-limit counter for a user.

    Returns (current_epoch, count). Raises on Redis failure.
    """
    now = int(time.time())
    count = await _bump(
        f"rego:hour:{user_id}:{now // settings.REGO_RATE_WINDOW_SECONDS}",
        settings.REGO_RATE_WINDOW_SECONDS * _BUMP_TTL_MULTIPLIER,
    )
    return now, count
