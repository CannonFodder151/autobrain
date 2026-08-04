"""Shared FastAPI dependencies."""

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User

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


async def require_paid(user: User = Depends(get_current_user)) -> User:
    """Free accounts cannot export files or use rego lookup."""
    if user.free_account:
        raise HTTPException(
            status_code=403,
            detail="Exporting and rego lookup are disabled on the free plan. Upgrade to enable them.",
        )
    return user


async def require_admin_api_key(request: Request) -> None:
    """Machine-to-machine admin access via X-Admin-API-Key header.

    Disabled unless ADMIN_API_KEY is set in the environment.
    """
    if not settings.ADMIN_API_KEY:
        raise HTTPException(status_code=503, detail="Admin API is not configured")
    supplied = request.headers.get("X-Admin-API-Key", "")
    if not supplied or supplied != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing admin API key")
    return None
