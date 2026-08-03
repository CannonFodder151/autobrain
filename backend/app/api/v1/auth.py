"""Authentication routes: login (with MFA), MFA management, admin user creation."""

import base64
import io

import pyotp
import qrcode
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_mfa_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    LoginResult,
    MfaCodeRequest,
    MfaSetupResponse,
    MfaVerifyRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshRequest,
    TokenPair,
    UserCreate,
    UserLogin,
    UserOut,
    UserWithVehicleCount,
)
from app.services import email as mail

router = APIRouter(prefix="/auth", tags=["auth"])

MFA_ISSUER = "AutoBrain"


# --- login / MFA ---
@router.post("/login", response_model=LoginResult)
async def login(payload: UserLogin, db: AsyncSession = Depends(get_db)) -> LoginResult:
    user = await db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    if user.mfa_enabled:
        if not payload.totp_code:
            return LoginResult(mfa_required=True, mfa_token=create_mfa_token(user.id))
        if not _verify_totp(user.mfa_secret, payload.totp_code):
            raise HTTPException(status_code=401, detail="Invalid MFA code")
    return LoginResult(token_pair=_token_pair(user))


@router.post("/mfa/verify", response_model=TokenPair)
async def mfa_verify(payload: MfaVerifyRequest, db: AsyncSession = Depends(get_db)) -> TokenPair:
    data = decode_token(payload.mfa_token)
    if not data or data.get("type") != "mfa":
        raise HTTPException(status_code=401, detail="Invalid or expired MFA session")
    user = await db.get(User, data.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid or expired MFA session")
    if not user.mfa_enabled or not _verify_totp(user.mfa_secret, payload.code):
        raise HTTPException(status_code=401, detail="Invalid MFA code")
    return _token_pair(user)


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenPair:
    data = decode_token(payload.refresh_token)
    if not data or data.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user = await db.get(User, data.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    return _token_pair(user)


@router.get("/me", response_model=UserWithVehicleCount)
async def me(
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserWithVehicleCount:
    from app.models.vehicle import Vehicle

    count = await db.scalar(
        select(func.count()).select_from(Vehicle).where(Vehicle.user_id == current.id)
    )
    count = count or 0
    remaining = max(current.max_vehicles - count, 0)
    return UserWithVehicleCount.model_validate(
        current, update={"vehicle_count": count, "vehicles_remaining": remaining}
    )


# --- MFA management (self-service, authenticated) ---
@router.get("/mfa/setup", response_model=MfaSetupResponse)
async def mfa_setup(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MfaSetupResponse:
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    otpauth_url = totp.provisioning_uri(name=user.email, issuer_name=MFA_ISSUER)
    qr = qrcode.make(otpauth_url)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    # Persist the pending secret; enable() verifies then activates it.
    user.mfa_secret = secret
    user.mfa_enabled = False
    await db.commit()
    return MfaSetupResponse(secret=secret, otpauth_url=otpauth_url, qr_data_url=data_url)


@router.post("/mfa/enable", response_model=UserOut)
async def mfa_enable(
    payload: MfaCodeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> User:
    if not user.mfa_secret or not _verify_totp(user.mfa_secret, payload.code):
        raise HTTPException(status_code=400, detail="Invalid MFA code")
    user.mfa_enabled = True
    await db.commit()
    await db.refresh(user)
    await mail.send_security_alert(
        user.email, user.display_name,
        "Two-factor authentication (MFA) was enabled on your account.",
    )
    return user


@router.post("/mfa/disable", response_model=UserOut)
async def mfa_disable(
    payload: MfaCodeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> User:
    if not user.mfa_enabled or not _verify_totp(user.mfa_secret, payload.code):
        raise HTTPException(status_code=400, detail="Invalid MFA code")
    user.mfa_enabled = False
    user.mfa_secret = None
    await db.commit()
    await db.refresh(user)
    await mail.send_security_alert(
        user.email, user.display_name,
        "Two-factor authentication (MFA) was disabled on your account.",
    )
    return user


# --- self-service password reset ---
@router.post("/password-reset/request", status_code=200)
async def request_password_reset(
    payload: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Send a password-reset email. Always returns 200 (do not reveal account existence)."""
    user = await db.scalar(select(User).where(User.email == payload.email.lower()))
    if user and user.is_active:
        token = create_password_reset_token(user.id)
        await mail.send_password_reset(user.email, user.display_name, token, settings.APP_BASE_URL)
    return {"message": "If that email exists, a reset link has been sent."}


@router.post("/password-reset/confirm", response_model=UserOut)
async def confirm_password_reset(
    payload: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db),
) -> User:
    data = decode_token(payload.token)
    if not data or data.get("type") != "password_reset":
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    user = await db.get(User, data.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    user.hashed_password = hash_password(payload.new_password)
    await db.commit()
    await db.refresh(user)
    await mail.send_password_changed(user.email, user.display_name)
    return user


# --- user provisioning (admin only — no self-signup) ---
@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def admin_create_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> TokenPair:
    """Create a user account. Admin-only: users cannot sign up themselves."""
    existing = await db.scalar(select(User).where(User.email == payload.email.lower()))
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        email=payload.email.lower(),
        display_name=payload.display_name,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        max_vehicles=payload.max_vehicles,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _token_pair(user)


# --- helpers ---
def _verify_totp(secret: str | None, code: str) -> bool:
    if not secret:
        return False
    try:
        return pyotp.TOTP(secret).verify(code, valid_window=1)
    except Exception:
        return False


def _token_pair(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=UserOut.model_validate(user),
    )
