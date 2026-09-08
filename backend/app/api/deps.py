"""Shared FastAPI dependencies."""

import hmac
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, WebSocket, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decode_token
from app.db.session import get_db
from app.models.device import Device
from app.models.user import User
from app.services.device_keys import key_prefix, verify_key

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

_credentials_exc = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise _credentials_exc
    user_id = payload.get("sub")
    if not user_id:
        raise _credentials_exc
    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise _credentials_exc
    if payload.get("ver", 0) != user.token_version:
        raise _credentials_exc
    return user


def _extract_ws_token(ws: WebSocket) -> str | None:
    """Pull a bearer token from the handshake: query param or Authorization header.

    The query-param form is accepted for browser-based WS clients that cannot
    set headers. Tokens are short-lived access JWTs.
    """
    token = ws.query_params.get("token")
    if token:
        return token
    auth = ws.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


async def authenticate_ws(ws: WebSocket, db: AsyncSession) -> User | None:
    """Authenticate a WebSocket handshake. Returns the User, or None to reject.

    Fail closed: no token, unverifiable token, non-access token, or inactive/
    unknown user all reject. Identity is taken from the token, never from the
    URL path.
    """
    token = _extract_ws_token(ws)
    if not token:
        return None
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    user = await db.get(User, user_id)
    if not user or not user.is_active:
        return None
    if payload.get("ver", 0) != user.token_version:
        return None
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user


async def require_write(user: User = Depends(get_current_user)) -> User:
    """Demo accounts are read-only: reject any mutating request."""
    if user.role == "demo":
        raise HTTPException(
            status_code=403,
            detail="This is a read-only demo account. Sign up or self-host to make changes.",
        )
    return user


async def require_ai(user: User = Depends(get_current_user)) -> User:
    """Demo and free accounts cannot call AI features."""
    if user.role == "demo":
        raise HTTPException(
            status_code=403,
            detail="AI features are disabled on the demo account.",
        )
    if user.free_account:
        raise HTTPException(
            status_code=403,
            detail="AI features are disabled on the free plan. Upgrade to enable them.",
        )
    return user


async def require_premium(user: User = Depends(get_current_user)) -> User:
    """Community Garage premium entitlement (AUT-294 rev 4).

    Free accounts are locked out of every social route server-side. Demo
    accounts keep read-only access (their curated demo feed) — write routes
    reject the demo role via `require_premium_write`.
    """
    if user.free_account:
        raise HTTPException(
            status_code=403,
            detail="Community Garage is a premium feature. Upgrade to enable it.",
        )
    return user


async def require_premium_write(
    user: User = Depends(require_premium),
    _read_only: User = Depends(require_write),
) -> User:
    """Social write routes: premium + not demo + not social-banned.

    Banned users are blocked from posting, commenting and flagging (AUT-832
    moderation hub); they keep read access.
    """
    if user.social_banned:
        raise HTTPException(
            status_code=403,
            detail="Your account has been suspended from posting in Community Garage.",
        )
    return user


async def require_rego(user: User = Depends(get_current_user)) -> User:
    """Free accounts cannot use rego lookup (exports are available on all plans)."""
    if user.free_account:
        raise HTTPException(
            status_code=403,
            detail="Rego lookup is disabled on the free plan. Upgrade to enable it.",
        )
    return user


async def require_admin_api_key(request: Request) -> None:
    """Machine-to-machine admin access via X-Admin-API-Key header.

    Disabled unless ADMIN_API_KEY is set in the environment.
    """
    if not settings.ADMIN_API_KEY:
        raise HTTPException(status_code=503, detail="Admin API is not configured")
    supplied = request.headers.get("X-Admin-API-Key", "")
    if not supplied or not hmac.compare_digest(supplied, settings.ADMIN_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing admin API key")
    return None


async def verify_dongle_server(request: Request) -> None:
    """Machine-to-machine backchannel auth from the dongle-server.

    The dongle-server sends its own DONGLE_SERVER_API_KEY as X-Internal-Api-Key
    when it calls /devices/verify; we check it against our configured value so
    only the legitimate dongle-server can ask for paid-gate verification.
    """
    if not settings.DONGLE_SERVER_API_KEY:
        raise HTTPException(status_code=503, detail="Dongle-server backchannel is not configured")
    supplied = request.headers.get("X-Internal-Api-Key", "")
    if not supplied or not hmac.compare_digest(supplied, settings.DONGLE_SERVER_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing internal API key")
    return None


async def get_device_from_key(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Device:
    """Unattended device auth via X-Device-API-Key (dongle WiFi upload, AUT-918).

    The raw key maps to a `devices` row by its short prefix index, then the
    supplied key is verified against the stored sha256 digest in constant
    time. The dongle carries only device id + key — no user JWT.
    """
    supplied = request.headers.get("X-Device-API-Key", "")
    if not supplied:
        raise HTTPException(
            status_code=401,
            detail="Missing X-Device-API-Key header",
            headers={"WWW-Authenticate": "DeviceKey"},
        )
    candidates = list(
        (
            await db.scalars(
                select(Device).where(Device.api_key_prefix == key_prefix(supplied))
            )
        ).all()
    )
    device = next(
        (d for d in candidates if verify_key(supplied, d.api_key_hash)), None
    )
    if device is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired device API key",
            headers={"WWW-Authenticate": "DeviceKey"},
        )
    return device


async def get_ha_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Home Assistant token auth via X-HA-API-Key (AUT-2541).

    The token maps to an `ha_integrations` row by its prefix index, then the
    full key is verified against the stored sha256 digest in constant time.
    Returns the owning User; updates last_used_at on every valid call.
    """
    from app.models.ha import HaIntegration
    from app.services.ha_keys import key_prefix, verify_key

    supplied = request.headers.get("X-HA-API-Key", "")
    if not supplied:
        raise HTTPException(
            status_code=401,
            detail="Missing X-HA-API-Key header",
            headers={"WWW-Authenticate": "HAKey"},
        )
    candidates = list(
        (
            await db.scalars(
                select(HaIntegration).where(HaIntegration.api_key_prefix == key_prefix(supplied))
            )
        ).all()
    )
    integration = next(
        (i for i in candidates if verify_key(supplied, i.api_key_hash)), None
    )
    if integration is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired HA API key",
            headers={"WWW-Authenticate": "HAKey"},
        )
    integration.last_used_at = datetime.now(timezone.utc)
    await db.commit()
    user = await db.get(User, integration.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid or expired HA API key")
    return user
