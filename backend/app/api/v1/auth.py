"""Authentication routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    RefreshRequest,
    TokenPair,
    UserCreate,
    UserLogin,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)) -> TokenPair:
    existing = await db.scalar(select(User).where(User.email == payload.email.lower()))
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        email=payload.email.lower(),
        display_name=payload.display_name,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _token_pair(user)


@router.post("/login", response_model=TokenPair)
async def login(payload: UserLogin, db: AsyncSession = Depends(get_db)) -> TokenPair:
    user = await db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return _token_pair(user)


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenPair:
    data = decode_token(payload.refresh_token)
    if not data or data.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user = await db.get(User, data.get("sub"))
    if not user:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    return _token_pair(user)


@router.get("/me", response_model=UserOut)
async def me(current: User = Depends(get_current_user)) -> User:
    return current


def _token_pair(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=UserOut.model_validate(user),
    )
