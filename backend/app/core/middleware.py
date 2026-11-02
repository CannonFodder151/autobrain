"""Security middleware: headers, rate limiting, API key auth, error handling, request size limits."""

from __future__ import annotations

import os
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.security import (
    _extract_key,
    _load_keys,
    _verify_key,
    add_security_headers,
    audit,
    RateLimiter,
)

_load_keys()

# Paths that don't require authentication (read-only health/metadata).
PUBLIC_PATHS = {"/health", "/api", "/openapi.json", "/docs", "/redoc"}

# Admin paths require authentication.
ADMIN_PREFIX = "/api/v1/admin"

# Rate limiter: 120 requests per minute per API key.
limiter = RateLimiter(max_requests=120, window_seconds=60)

# Max request body size (10KB) - prevents DoS via large payloads.
MAX_BODY_SIZE = 10 * 1024

# Trusted reverse proxies (comma-separated IPs/CIDRs). When set, requests from
# any other client IP are rejected before processing (REGO-012). In production
# this must be configured; in dev it may be empty to allow local testing.
_TRUSTED_PROXIES_RAW = os.environ.get("TRUSTED_PROXIES", "")
TRUSTED_PROXIES = {
    p.strip() for p in _TRUSTED_PROXIES_RAW.split(",") if p.strip()
}


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        # Generate/request correlation ID for tracing.
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())[:8]
        request.state.correlation_id = correlation_id

        # Trusted proxy enforcement (REGO-012): if TRUSTED_PROXIES configured,
        # reject requests not from a trusted proxy to mitigate IP spoofing.
        client_host = request.client.host if request.client else None
        if TRUSTED_PROXIES:
            if client_host not in TRUSTED_PROXIES:
                audit("proxy_not_trusted", request, client_host=client_host or "unknown")
                resp = JSONResponse(
                    status_code=403,
                    content={"detail": "Forbidden"},
                )
                add_security_headers(resp)
                resp.headers["X-Correlation-ID"] = correlation_id
                return resp

        # Request body size limit (enforced before reading body).
        content_length = request.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_BODY_SIZE:
            audit("body_size_exceeded", request, size=content_length)
            resp = JSONResponse(
                status_code=413,
                content={"detail": f"Request body too large. Max {MAX_BODY_SIZE} bytes."},
            )
            add_security_headers(resp)
            resp.headers["X-Correlation-ID"] = correlation_id
            return resp

        # Rate limiting (keyed by API key or client IP).
        key = _extract_key(request) or (request.client.host if request.client else "unknown")
        allowed, remaining = limiter.check(key)
        if not allowed:
            audit("rate_limit_exceeded", request, key=key)
            resp = JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Retry later."},
            )
            add_security_headers(resp)
            resp.headers["Retry-After"] = str(limiter.window_seconds)
            resp.headers["X-Correlation-ID"] = correlation_id
            return resp

        # Authentication for admin endpoints.
        if path.startswith(ADMIN_PREFIX):
            api_key = _extract_key(request)
            key_id = _verify_key(api_key)
            if key_id is None:
                audit("unauthorized_access", request, path=path)
                resp = JSONResponse(
                    status_code=401,
                    content={"detail": "Authentication required."},
                    headers={"WWW-Authenticate": "Bearer"},
                )
                add_security_headers(resp)
                resp.headers["X-Correlation-ID"] = correlation_id
                return resp
            audit("admin_access", request, key_id=key_id)
            request.state.api_key_id = key_id

        # Authentication for other non-public, non-health endpoints in production.
        # For this project, require API key only for admin; read endpoints stay open.
        if path not in PUBLIC_PATHS and not path.startswith("/api/v1/"):
            if _extract_key(request) is None and path not in PUBLIC_PATHS:
                pass  # allow public read

        response = await call_next(request)

        # Add security headers to all responses.
        add_security_headers(response)

        # Add rate limit headers.
        response.headers["X-RateLimit-Limit"] = str(limiter.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-Correlation-ID"] = correlation_id

        return response


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            return await call_next(request)
        except Exception:
            import logging

            correlation_id = getattr(request.state, "correlation_id", "unknown")
            logging.getLogger("vehicle_health_api").exception(
                "Unhandled error on %s %s [correlation_id=%s]",
                request.method, request.url.path, correlation_id
            )
            resp = JSONResponse(
                status_code=500,
                content={"detail": "Internal server error."},
            )
            add_security_headers(resp)
            resp.headers["X-Correlation-ID"] = correlation_id
            return resp