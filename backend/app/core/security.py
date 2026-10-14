"""Security helpers: password hashing and JWT tokens."""

import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(plain: str, hashed: str) -> bool:
    pwd_bytes = plain.encode('utf-8')
    hashed_bytes = hashed.encode('utf-8')
    return bcrypt.checkpw(pwd_bytes, hashed_bytes)


def create_access_token(
    subject: str | int, token_version: int = 0, expires_minutes: int | None = None
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    return jwt.encode(
        {
            "sub": str(subject),
            "exp": expire,
            "type": "access",
            "ver": token_version,
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def create_mfa_token(subject: str | int) -> str:
    """Short-lived token granting a login in progress (MFA step only)."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=5)
    return jwt.encode(
        {"sub": str(subject), "exp": expire, "type": "mfa"},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def create_password_reset_token(subject: str | int) -> str:
    """Short-lived token that authorises a password reset (30 min)."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=30)
    return jwt.encode(
        {"sub": str(subject), "exp": expire, "type": "password_reset"},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def create_invite_token(subject: str | int, days: int = 7) -> str:
    """Long-lived token authorising an invited user to set their password (7 days)."""
    expire = datetime.now(timezone.utc) + timedelta(days=days)
    return jwt.encode(
        {"sub": str(subject), "exp": expire, "type": "invite"},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def create_refresh_token(subject: str | int, token_version: int = 0) -> str:
    """Long-lived refresh token with a random `jti` (for rotation/revocation).

    Carries the user's `token_version` at issue time: bumping the version on
    logout/password change invalidates every token minted before it. Rotation
    on each refresh mints a fresh `jti`, so a stolen token stops working the
    moment it is replayed (or the account is logged out).
    """
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return jwt.encode(
        {
            "sub": str(subject),
            "exp": expire,
            "type": "refresh",
            "jti": uuid.uuid4().hex,
            "ver": token_version,
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except jwt.InvalidTokenError:
        return None
