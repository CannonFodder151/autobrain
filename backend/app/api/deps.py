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
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

_credentials_exc = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme_optional),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Authenticate via JWT bearer token, falling back to X-API-Key.

    Public REST endpoints accept either a session JWT or a developer API key.
    When no bearer token is supplied, the request is authenticated with the
    X-API-Key header if present; otherwise the original 401 is raised.
    """
    if token:
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

    # No bearer token — try API key
    if request.headers.get("X-API-Key"):
        return await get_user_from_api_key(request, db)

    raise _credentials_exc


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


async def require_write(
    request: Request = None,
    user: User = Depends(get_current_user),
) -> User:
    """Demo accounts are read-only: reject any mutating request.

    When authenticated via an API key, the key must also carry a write scope
    (write:vehicles, write:services, write:fuel, write:diagnostics,
    write:logbook, or admin:keys). JWT-authenticated users are governed by the
    existing demo/free-account rules.
    """
    from app.services.api_keys import has_scope

    if user.role == "demo":
        raise HTTPException(
            status_code=403,
            detail="This is a read-only demo account. Sign up or self-host to make changes.",
        )

    if request is not None:
        key = getattr(request.state, "api_key", None)
        if key is not None:
            write_scopes = (
                "write:vehicles",
                "write:services",
                "write:fuel",
                "write:diagnostics",
                "write:logbook",
                "admin:keys",
            )
            if not any(has_scope(key, s) for s in write_scopes):
                raise HTTPException(
                    status_code=403,
                    detail="API key missing a write scope",
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


async def get_user_from_api_key(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Authenticate a request via X-API-Key header.

    Returns the owning User if valid. Raises 401 if invalid/missing.
    """
    from app.services.api_keys import find_key_by_raw, touch_last_used

    supplied = request.headers.get("X-API-Key", "")
    if not supplied:
        raise HTTPException(
            status_code=401,
            detail="Missing X-API-Key header",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    key = await find_key_by_raw(db, supplied)
    if not key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or revoked API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Check rate limit for this specific key
    await check_api_key_rate_limit(db, key)

    # Update last_used_at
    await touch_last_used(db, key)

    # Get the user
    user = await db.get(User, key.user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=401,
            detail="Invalid or revoked API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Attach key info to request state for scope checks
    request.state.api_key = key
    return user


async def check_api_key_rate_limit(db: AsyncSession, key) -> None:
    """Enforce per-key rate limit using Redis."""
    if not key.rate_limit or not key.rate_window_seconds:
        return  # No limit configured

    from app.core.config import settings
    from app.core.logging import get_logger
    from app.services.rate_limit import _client as _redis_client

    logger = get_logger(__name__)
    r = _redis_client()
    try:
        now = int(datetime.now(timezone.utc).timestamp())
        window_key = f"apikey:{key.id}:{now // key.rate_window_seconds}"
        pipe = r.pipeline()
        pipe.incr(window_key)
        pipe.expire(window_key, key.rate_window_seconds * 2)
        count = int((await pipe.execute())[0])

        if count > key.rate_limit:
            logger.warning("api_key_rate_limit_exceeded", key_id=key.id, count=count, limit=key.rate_limit)
            raise HTTPException(
                status_code=429,
                detail=f"API key rate limit exceeded ({key.rate_limit} requests per {key.rate_window_seconds}s)",
                headers={"Retry-After": str(key.rate_window_seconds)},
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("api_key_rate_limit_unavailable", key_id=key.id, error=str(exc))
        # Fail open for rate limit (don't block legitimate traffic if Redis is down)
    finally:
        await r.aclose()


def require_scope(scope: str):
    """Dependency factory to require a specific scope on the API key."""
    async def _check(
        request: Request,
        user: User = Depends(get_user_from_api_key),
    ) -> User:
        from app.services.api_keys import has_scope
        key = getattr(request.state, "api_key", None)
        if not key or not has_scope(key, scope):
            raise HTTPException(
                status_code=403,
                detail=f"API key missing required scope: {scope}",
            )
        return user
    return _check


async def get_current_user_or_api_key(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Authenticate via API key (X-API-Key) if present, else JWT bearer token."""
    if request.headers.get("X-API-Key"):
        return await get_user_from_api_key(request, db)
    # Fall back to JWT
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


async def require_write_or_api_key(
    request: Request,
    user: User = Depends(get_current_user_or_api_key),
) -> User:
    """Allow writes for authenticated users (not demo) or API keys with write scope."""
    from app.services.api_keys import has_scope
    key = getattr(request.state, "api_key", None)
    if key:
        # API key path: check for any write scope
        write_scopes = {"write:vehicles", "write:services", "write:fuel", "write:diagnostics", "write:logbook", "admin:keys"}
        for s in write_scopes:
            if has_scope(key, s):
                return user
        raise HTTPException(status_code=403, detail="API key missing write scope")
    # JWT path: original behavior
    if user.role == "demo":
        raise HTTPException(
            status_code=403,
            detail="This is a read-only demo account. Sign up or self-host to make changes.",
        )
    return user
