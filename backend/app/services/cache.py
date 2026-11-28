"""Redis-based caching utilities for API responses."""

import hashlib
import json
import logging
from typing import Any, Callable, Optional, TypeVar

from redis.asyncio import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

_DEFAULT_TTL = 300  # 5 minutes
_MAX_TTL = 86400  # 24 hours


def _redis_client() -> Redis:
    return Redis.from_url(settings.REDIS_URL, decode_responses=True)


def _cache_key(prefix: str, *parts: str) -> str:
    """Generate a cache key from parts."""
    key_parts = [prefix] + [str(p) for p in parts]
    raw = ":".join(key_parts)
    if len(raw) > 200:
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
        return f"{prefix}:hash:{digest}"
    return raw


async def cache_get(key: str) -> Optional[str]:
    """Get a value from Redis cache."""
    r = _redis_client()
    try:
        return await r.get(key)
    except Exception as exc:
        logger.warning("cache_get_failed key=%s error=%s", key, exc)
        return None
    finally:
        await r.aclose()


async def cache_set(key: str, value: str, ttl: int = _DEFAULT_TTL) -> bool:
    """Set a value in Redis cache with TTL."""
    r = _redis_client()
    try:
        await r.setex(key, min(ttl, _MAX_TTL), value)
        return True
    except Exception as exc:
        logger.warning("cache_set_failed key=%s error=%s", key, exc)
        return False
    finally:
        await r.aclose()


async def cache_delete(key: str) -> bool:
    """Delete a key from Redis cache."""
    r = _redis_client()
    try:
        await r.delete(key)
        return True
    except Exception as exc:
        logger.warning("cache_delete_failed key=%s error=%s", key, exc)
        return False
    finally:
        await r.aclose()


async def cache_delete_pattern(pattern: str) -> int:
    """Delete all keys matching a pattern."""
    r = _redis_client()
    try:
        count = 0
        async for key in r.scan_iter(match=pattern):
            await r.delete(key)
            count += 1
        return count
    except Exception as exc:
        logger.warning("cache_delete_pattern_failed pattern=%s error=%s", pattern, exc)
        return 0
    finally:
        await r.aclose()


async def cached(
    key: str,
    ttl: int = _DEFAULT_TTL,
    serializer: Callable[[Any], str] = json.dumps,
    deserializer: Callable[[str], Any] = json.loads,
) -> Callable[[Callable[[], T]], Callable[[], T]]:
    """Decorator to cache an async function result in Redis."""
    
    def decorator(func: Callable[[], T]) -> Callable[[], T]:
        async def wrapper() -> T:
            cached_value = await cache_get(key)
            if cached_value is not None:
                try:
                    return deserializer(cached_value)
                except Exception as exc:
                    logger.warning("cache_deserialize_failed key=%s error=%s", key, exc)
            
            result = await func()
            try:
                await cache_set(key, serializer(result), ttl)
            except Exception as exc:
                logger.warning("cache_serialize_failed key=%s error=%s", key, exc)
            return result
        
        return wrapper
    
    return decorator


async def invalidate_vehicle_cache(vehicle_id: str) -> int:
    """Invalidate all cache entries related to a vehicle."""
    patterns = [
        f"vehicle:{vehicle_id}:*",
        f"valuation:{vehicle_id}:*",
        f"advisor:*:{vehicle_id}:*",
        f"search:*:{vehicle_id}:*",
    ]
    total = 0
    for pattern in patterns:
        total += await cache_delete_pattern(pattern)
    return total


async def invalidate_user_cache(user_id: str) -> int:
    """Invalidate all cache entries related to a user."""
    patterns = [
        f"user:{user_id}:*",
        f"vehicles:{user_id}:*",
    ]
    total = 0
    for pattern in patterns:
        total += await cache_delete_pattern(pattern)
    return total