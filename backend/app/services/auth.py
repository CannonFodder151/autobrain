"""Auth business logic: login/MFA/TOTP helpers and rate limiting.

Extracted from api/v1/auth.py so the router stays thin and these rules are
unit-testable (AUT-126 #12).
"""

import base64
import io
import secrets
import time
from collections import defaultdict, deque

import pyotp
import qrcode
from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
)
from app.models.user import User
from app.schemas.auth import MfaSetupResponse, TokenPair, UserOut

MFA_ISSUER = "AutoBrain"

# --- brute-force protection: failed logins per IP ---
_login_failures: dict[str, deque[float]] = defaultdict(deque)


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(ip: str) -> None:
    now = time.monotonic()
    q = _login_failures[ip]
    while q and now - q[0] > settings.LOGIN_WINDOW_SECONDS:
        q.popleft()
    if len(q) >= settings.LOGIN_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts. Try again in 3 hours.",
        )


def record_failure(ip: str) -> None:
    _login_failures[ip].append(time.monotonic())


def clear_failures(ip: str) -> None:
    _login_failures.pop(ip, None)


def verify_totp(secret: str | None, code: str) -> bool:
    if not secret:
        return False
    try:
        return pyotp.TOTP(secret).verify(code, valid_window=1)
    except Exception:
        return False


def token_pair(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
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
