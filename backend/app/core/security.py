"""Security core: API key auth, security headers, rate limiting, error handling."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from collections import defaultdict
from typing import Optional

from fastapi import Request, Response

logger = logging.getLogger("vehicle_health_api")

# ---------------------------------------------------------------------------
# API key auth
# ---------------------------------------------------------------------------

# API keys are SHA-256 hashes of raw secrets, never stored in plaintext.
# Keys are read from the API_KEYS env var (comma-separated "id:secret" pairs)
# or a single API_KEY env var for the default admin key.
_API_KEYS: dict[str, str] = {}  # api_key_id -> sha256(secret)
_ADMIN_KEY_HASH: Optional[str] = None


def _load_keys() -> None:
    global _API_KEYS, _ADMIN_KEY_HASH
    if _API_KEYS:
        return
    raw = os.environ.get("API_KEYS", "")
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        kid, secret = pair.split(":", 1)
        _API_KEYS[kid.strip()] = hashlib.sha256(secret.strip().encode()).hexdigest()
    admin = os.environ.get("API_KEY", "")
    if admin:
        _ADMIN_KEY_HASH = hashlib.sha256(admin.encode()).hexdigest()
    if not _API_KEYS and not _ADMIN_KEY_HASH:
        # No keys configured: fail closed for admin, allow read-only health.
        logger.warning("No API keys configured — admin endpoints will be unreachable")


def _verify_key(api_key: Optional[str]) -> Optional[str]:
    """Return the key id if valid, else None."""
    if not api_key:
        return None
    if ":" in api_key:
        kid, secret = api_key.split(":", 1)
        expected = _API_KEYS.get(kid.strip())
        if expected and hmac.compare_digest(expected, hashlib.sha256(secret.strip().encode()).hexdigest()):
            return kid.strip()
    # single-token fallback (no id prefix)
    if _ADMIN_KEY_HASH and hmac.compare_digest(_ADMIN_KEY_HASH, hashlib.sha256(api_key.encode()).hexdigest()):
        return "admin"
    return None


def _extract_key(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return request.headers.get("X-API-Key")


# ---------------------------------------------------------------------------
# Rate limiting (in-memory, per API key)
# ---------------------------------------------------------------------------

class RateLimiter:
    def __init__(self, max_requests: int = 60, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._counts: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str) -> tuple[bool, int]:
        now = time.monotonic()
        window_start = now - self.window_seconds
        timestamps = self._counts[key]
        timestamps[:] = [t for t in timestamps if t > window_start]
        if len(timestamps) >= self.max_requests:
            return False, 0
        timestamps.append(now)
        remaining = self.max_requests - len(timestamps)
        return True, remaining


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
    "Server": "",  # hide server identity
}


def add_security_headers(response: Response) -> None:
    for k, v in SECURITY_HEADERS.items():
        if v:
            response.headers[k] = v
        else:
            try:
                del response.headers[k]
            except KeyError:
                pass


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------

AUDIT_EVENTS = {
    "auth_success",
    "auth_failure",
    "admin_access",
    "rate_limit_exceeded",
    "unauthorized_access",
    "proxy_not_trusted",
    "body_size_exceeded",
}


def audit(event: str, request: Request, **fields: object) -> None:
    if event not in AUDIT_EVENTS:
        return
    payload = {
        "event": event,
        "ts": time.time(),
        "ip": request.client.host if request.client else "unknown",
        "path": request.url.path,
        "method": request.method,
    }
    payload.update({k: str(v) for k, v in fields.items()})
    logger.info(json.dumps(payload))