"""Auth API routes for AutoBrain Shop."""

import hmac
import secrets
import pyotp
import qrcode
import io
import base64
from datetime import datetime, timezone, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.db.session import get_db
from app.models.workshop import WorkshopUser, WorkshopRole
from app.schemas.auth import (
    WorkshopUserLogin,
    WorkshopUserOut,
    TokenPair,
    LoginResult,
    RefreshRequest,
    MfaVerifyRequest,
    MfaSetupResponse,
    PasswordResetRequest,
    PasswordResetConfirm,
)

router = APIRouter(prefix="/auth", tags=["auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


_credentials_exc = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkshopUser:
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise _credentials_exc
    user_id = payload.get("sub")
    if not user_id:
        raise _credentials_exc
    user = await db.get(WorkshopUser, user_id)
    if not user or not user.is_active:
        raise _credentials_exc
    if payload.get("ver", 0) != user.token_version:
        raise _credentials_exc
    return user


async def get_current_workshop(
    user: Annotated[WorkshopUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Workshop:
    workshop = await db.get(Workshop, user.workshop_id)
    if not workshop or not workshop.is_active:
        raise HTTPException(status_code=403, detail="Workshop not found or inactive")
    return workshop


@router.post("/login", response_model=LoginResult)
async def login(
    credentials: WorkshopUserLogin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoginResult:
    result = await db.execute(
        select(WorkshopUser).where(WorkshopUser.email == credentials.email)
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    # Check workshop status
    workshop = await db.get(Workshop, user.workshop_id)
    if not workshop or not workshop.is_active:
        raise HTTPException(status_code=403, detail="Workshop is inactive")

    # MFA check
    if user.mfa_enabled:
        if not credentials.totp_code:
            mfa_token = create_access_token(
                subject=user.id,
                token_version=user.token_version,
                expires_delta=timedelta(minutes=5),
            )
            return LoginResult(
                mfa_required=True,
                mfa_token=mfa_token,
            )
        totp = pyotp.TOTP(user.mfa_secret)
        if not totp.verify(credentials.totp_code, valid_window=1):
            raise HTTPException(status_code=401, detail="Invalid 2FA code")

    # Generate tokens
    access_token = create_access_token(subject=user.id, token_version=user.token_version)
    refresh_token = create_refresh_token(subject=user.id)

    # Update last login
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    user_out = WorkshopUserOut.model_validate(user)
    return LoginResult(
        token_pair=TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            user=user_out,
        )
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    request: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenPair:
    payload = decode_token(request.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise _credentials_exc
    user_id = payload.get("sub")
    if not user_id:
        raise _credentials_exc
    user = await db.get(WorkshopUser, user_id)
    if not user or not user.is_active:
        raise _credentials_exc

    access_token = create_access_token(subject=user.id, token_version=user.token_version)
    refresh_token = create_refresh_token(subject=user.id)
    user_out = WorkshopUserOut.model_validate(user)
    return TokenPair(access_token=access_token, refresh_token=refresh_token, user=user_out)


@router.post("/mfa/setup", response_model=MfaSetupResponse)
async def mfa_setup(
    user: Annotated[WorkshopUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MfaSetupResponse:
    secret = pyotp.random_base32()
    user.mfa_secret = secret
    await db.commit()

    totp = pyotp.TOTP(secret)
    otpauth_url = totp.provisioning_uri(
        name=user.email, issuer_name="AutoBrain Shop"
    )

    # Generate QR code
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(otpauth_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_data_url = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"

    return MfaSetupResponse(
        secret=secret,
        otpauth_url=otpauth_url,
        qr_data_url=qr_data_url,
    )


@router.post("/mfa/verify")
async def mfa_verify(
    request: MfaVerifyRequest,
    user: Annotated[WorkshopUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, bool]:
    if not user.mfa_secret:
        raise HTTPException(status_code=400, detail="MFA not set up")

    totp = pyotp.TOTP(user.mfa_secret)
    if not totp.verify(request.code, valid_window=1):
        raise HTTPException(status_code=401, detail="Invalid 2FA code")

    user.mfa_enabled = True
    await db.commit()
    return {"enabled": True}


@router.post("/mfa/disable")
async def mfa_disable(
    request: MfaVerifyRequest,
    user: Annotated[WorkshopUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, bool]:
    if not user.mfa_enabled:
        raise HTTPException(status_code=400, detail="MFA not enabled")

    totp = pyotp.TOTP(user.mfa_secret)
    if not totp.verify(request.code, valid_window=1):
        raise HTTPException(status_code=401, detail="Invalid 2FA code")

    user.mfa_enabled = False
    user.mfa_secret = None
    user.token_version += 1  # revoke all tokens
    await db.commit()
    return {"disabled": True}


@router.post("/password-reset")
async def password_reset(
    request: PasswordResetRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    # Always return success to avoid email enumeration
    result = await db.execute(
        select(WorkshopUser).where(WorkshopUser.email == request.email)
    )
    user = result.scalar_one_or_none()
    if user:
        # TODO: send reset email with token
        pass
    return {"message": "If the email exists, a reset link has been sent"}


@router.post("/password-reset/confirm")
async def password_reset_confirm(
    request: PasswordResetConfirm,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    # TODO: verify token from email
    # For now, just return success
    return {"message": "Password has been reset"}


@router.get("/me", response_model=WorkshopUserOut)
async def me(
    user: Annotated[WorkshopUser, Depends(get_current_user)],
) -> WorkshopUserOut:
    return WorkshopUserOut.model_validate(user)