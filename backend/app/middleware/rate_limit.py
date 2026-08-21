"""Global per-IP rate limiting middleware (AB-06).

Fixed-window Redis counters keyed by IP + route pattern. Applied to all
requests before route handlers. Per-route overrides (signup, password-reset)
tighten the default window. Fail-open on Redis unavailability to avoid
locking out the entire API during a Redis outage.
"""

import time
from collections.abc import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Default limits: 60 req/min per IP
DEFAULT_LIMIT = 60
DEFAULT_WINDOW = 60

# Per-route overrides (method + path pattern -> (limit, window_seconds))
# Path patterns are matched with startswith on the normalized route
ROUTE_LIMITS: dict[tuple[str, str], tuple[int, int]] = {
    ("POST", "/api/v1/auth/signup"): (5, 60),
    ("POST", "/api/v1/auth/password-reset/request"): (3, 60),
    ("POST", "/api/v1/auth/login"): (10, 60),
    ("POST", "/api/v1/auth/mfa/verify"): (10, 60),
    ("POST", "/api/v1/auth/mfa/complete-setup"): (10, 60),
}


def _client() -> Redis:
    return Redis.from_url(settings.REDIS_URL, decode_responses=True)


def _match_route(method: str, path: str) -> tuple[int, int] | None:
    """Find the most specific route limit for this request."""
    # Exact match first
    key = (method, path)
    if key in ROUTE_LIMITS:
        return ROUTE_LIMITS[key]
    # Prefix match for dynamic routes (e.g., /api/v1/vehicles/...)
    for (m, pattern), limits in ROUTE_LIMITS.items():
        if m == method and path.startswith(pattern):
            return limits
    return None


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP rate limiting middleware."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)
        if request.url.path in ("/health", "/docs", "/redoc", "/openapi.json"):
            return await call_next(request)

        # Skip if already handled by route-level dependency (AI routes)
        if request.url.path.startswith("/api/v1/ai/"):
            return await call_next(request)

        ip = self._client_ip(request)
        method = request.method
        path = request.url.path

        route_limits = _match_route(method, path)
        limit, window = route_limits if route_limits else (DEFAULT_LIMIT, DEFAULT_WINDOW)

        redis_key = f"ratelimit:{ip}:{method}:{path}:{int(time.time()) // window}"

        r = _client()
        try:
            try:
                pipe = r.pipeline()
                pipe.incr(redis_key)
                pipe.expire(redis_key, window * 2)
                results = await pipe.execute()
                current = int(results[0])
            except Exception as exc:
                # Fail-open: if Redis is down, don't block requests
                logger.warning("rate_limit_redis_unavailable", ip=ip, error=str(exc))
                return await call_next(request)
        finally:
            await r.aclose()

        if current > limit:
            retry_after = window - (int(time.time()) % window)
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Please slow down.",
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + retry_after),
                },
            )

        # Add rate limit headers to successful responses
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - current))
        response.headers["X-RateLimit-Reset"] = str(int(time.time()) + window - (int(time.time()) % window))
        return response

    def _client_ip(self, request: Request) -> str:
        """Extract client IP, respecting X-Forwarded-For from trusted proxy."""
        # Check X-Forwarded-For (first IP is the original client)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        # Check X-Real-IP (nginx)
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        # Fallback to direct connection
        return request.client.host if request.client else "unknown"