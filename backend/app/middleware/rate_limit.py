"""Global per-IP rate limiting middleware (AUT-1187 AB-06).

Fixed-window counters in Redis, shared across backend workers. One global
default per IP plus exact-suffix per-route overrides (e.g. signup 5/min,
password-reset 3/min) so enumeration/credential-stuffing endpoints get tight
budgets without touching every router.

Fail-open on Redis outage: a limiter outage must not take the whole API down
(login/MFA keep their separate fail-closed brute-force limiter).
"""

import time

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Paths exempt from the global limiter (health checks, docs).
_EXEMPT = ("/health", "/docs", "/redoc", "/openapi.json")


def _client_ip(request: Request) -> str:
    # Same trust model as services.auth.client_ip: nginx sets X-Real-IP,
    # overwriting anything the client sent.
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    return request.client.host if request.client else "unknown"


def _route_limit(path: str) -> tuple[int, int]:
    """(max_requests, window_seconds) for this path; suffix match on the
    configured override keys, most specific (longest) wins."""
    matches = [(s, lim) for s, lim in settings.RATE_LIMIT_OVERRIDES.items() if path.endswith(s)]
    if matches:
        suffix, lim = max(matches, key=lambda m: len(m[0]))
        return lim
    return (settings.RATE_LIMIT_DEFAULT_PER_MINUTE, 60)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        if not settings.RATE_LIMIT_ENABLED or request.url.path in _EXEMPT:
            return await call_next(request)
        if request.method in ("GET", "HEAD") and request.url.path.startswith("/assets"):
            return await call_next(request)

        ip = _client_ip(request)
        path = request.url.path
        limit, window = _route_limit(path)

        now = int(time.time())
        key = f"ratelimit:{path}:{ip}:{now // window}"
        r = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            pipe = r.pipeline()
            pipe.incr(key)
            pipe.expire(key, window * 2)
            count = int((await pipe.execute())[0])
        except Exception as exc:
            logger.warning("rate_limit_unavailable", error=str(exc), path=path)
            return await call_next(request)
        finally:
            await r.aclose()

        headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(max(limit - count, 0)),
        }
        if count > limit:
            retry_after = window - (now % window)
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
                headers={**headers, "Retry-After": str(retry_after)},
            )
        response = await call_next(request)
        for k, v in headers.items():
            response.headers[k] = v
        return response