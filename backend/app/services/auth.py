"""Auth business logic: login/MFA/TOTP helpers and rate limiting.

Extracted from api/v1/auth.py so the router stays thin and these rules are
unit-testable (AUT-126 #12).
"""

import base64
import io
import secrets
import time

import pyotp
import qrcode
from fastapi import HTTPException, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
)
from app.models.user import User
from app.schemas.auth import MfaSetupResponse, TokenPair, UserOut

MFA_ISSUER = "AutoBrain"

logger = get_logger(__name__)

# --- brute-force protection: failed logins per IP + email (AUT-303) ---
# Counters live in Redis (shared across workers, survives restarts) as
# sliding-window sorted sets of failure timestamps. The client IP is read from
# the trusted proxy header X-Real-IP (nginx sets `X-Real-IP $remote_addr`,
# overwriting whatever the client sent); X-Forwarded-For's leading hops are
# attacker-controlled and are never trusted. Per-email counting is defense in
# depth against a misconfigured proxy where IP limits cannot be relied on. On
# Redis outage we fail open (log + skip) so a limiter outage cannot lock every
# user out of login.


def _redis() -> Redis:
    return Redis.from_url(settings.REDIS_URL, decode_responses=True)


def _fail_key(kind: str, value: str) -> str:
    return f"login:fail:{kind}:{value}"


def client_ip(request: Request) -> str:
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    return request.client.host if request.client else "unknown"


async def _failures_in_window(key: str, now: float) -> int:
    r = _redis()
    try:
        await r.zremrangebyscore(key, 0, now - settings.LOGIN_WINDOW_SECONDS)
        return await r.zcard(key)
    finally:
        await r.aclose()


async def _record_failure(key: str, now: float) -> None:
    r = _redis()
    try:
        pipe = r.pipeline()
        pipe.zadd(key, {f"{now}:{secrets.token_hex(4)}": now})
        pipe.expire(key, settings.LOGIN_WINDOW_SECONDS * 2)
        await pipe.execute()
    finally:
        await r.aclose()


async def check_rate_limit(ip: str, email: str | None = None) -> None:
    """Raise 429 when `ip` (and optionally `email`) is over the failure budget."""
    now = time.time()
    keys = [_fail_key("ip", ip)]
    if email:
        keys.append(_fail_key("email", email))
    try:
        for key in keys:
            if await _failures_in_window(key, now) >= settings.LOGIN_MAX_ATTEMPTS:
                raise HTTPException(
                    status_code=429,
                    detail="Too many failed login attempts. Try again in 3 hours.",
                )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("login_rate_limit_unavailable", error=str(exc))


async def record_failure(ip: str, email: str | None = None) -> None:
    now = time.time()
    keys = [_fail_key("ip", ip)]
    if email:
        keys.append(_fail_key("email", email))
    try:
        for key in keys:
            await _record_failure(key, now)
    except Exception as exc:
        logger.warning("login_rate_limit_record_failed", error=str(exc))


async def clear_failures(ip: str, email: str | None = None) -> None:
    keys = [_fail_key("ip", ip)]
    if email:
        keys.append(_fail_key("email", email))
    try:
        r = _redis()
        try:
            await r.delete(*keys)
        finally:
            await r.aclose()
    except Exception as exc:
        logger.warning("login_rate_limit_clear_failed", error=str(exc))


def verify_totp(secret: str | None, code: str) -> bool:
    if not secret:
        return False
    try:
        return pyotp.TOTP(secret).verify(code, valid_window=1)
    except Exception:
        return False


def token_pair(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_access_token(user.id, token_version=user.token_version),
        refresh_token=create_refresh_token(user.id, token_version=user.token_version),
        user=UserOut.model_validate(user),
    )


def build_mfa_setup(user: User) -> MfaSetupResponse:
    """Generate a fresh TOTP secret + QR; persists it on the user (pending enable)."""
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    otpauth_url = totp.provisioning_uri(name=user.email, issuer_name=MFA_ISSUER)
    qr = qrcode.make(otpauth_url)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    user.mfa_secret = secret
    user.mfa_enabled = False
    return MfaSetupResponse(secret=secret, otpauth_url=otpauth_url, qr_data_url=data_url)


async def resolve_mfa_session(db: AsyncSession, mfa_token: str) -> User:
    """Decode + load the user behind an MFA session token; 401 on any flaw."""
    data = decode_token(mfa_token)
    if not data or data.get("type") != "mfa":
        raise HTTPException(status_code=401, detail="Invalid or expired MFA session")
    user = await db.get(User, data.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid or expired MFA session")
    return user


def random_password() -> str:
    return hash_password(secrets.token_urlsafe(32))
