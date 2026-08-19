"""Authentication routes: login (with MFA), MFA management, admin user creation."""

import json as _json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin, require_write
from app.core.config import settings
from app.core.security import (
    create_invite_token,
    create_mfa_token,
    create_password_reset_token,
    hash_password,
)
from app.db.session import get_db
from app.models.refresh_token import RevokedRefreshToken
from app.models.user import User
from app.schemas.auth import (
    LoginResult,
    MfaCodeRequest,
    MfaSetupResponse,
    MfaSetupSessionRequest,
    MfaVerifyRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshRequest,
    SignupRequest,
    TokenPair,
    UserCreate,
    UserLogin,
    UserOut,
    UserWithVehicleCount,
)
from app.services import auth as auth_svc
from app.services import email as mail

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# --- login / MFA ---
@router.post("/login", response_model=LoginResult)
async def login(
    payload: UserLogin,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> LoginResult:
    ip = auth_svc.client_ip(request)
    await auth_svc.check_rate_limit(ip, payload.email)
    user = await db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not _verify_password(payload.password, user.hashed_password):
        await auth_svc.record_failure(ip, payload.email)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    # MFA enforcement: every non-demo account must have MFA enabled.
    if settings.MFA_ENFORCED and user.role != "demo" and not user.mfa_enabled:
        return LoginResult(
            mfa_setup_required=True,
            mfa_token=create_mfa_token(user.id),
        )

    if user.mfa_enabled:
        if not payload.totp_code:
            return LoginResult(mfa_required=True, mfa_token=create_mfa_token(user.id))
        if not auth_svc.verify_totp(user.mfa_secret, payload.totp_code):
            await auth_svc.record_failure(ip, user.email)
            raise HTTPException(status_code=401, detail="Invalid MFA code")
    await auth_svc.clear_failures(ip, user.email)
    return LoginResult(token_pair=auth_svc.token_pair(user))


@router.post("/mfa/verify", response_model=TokenPair)
async def mfa_verify(
    payload: MfaVerifyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    ip = auth_svc.client_ip(request)
    await auth_svc.check_rate_limit(ip)
    user = await auth_svc.resolve_mfa_session(db, payload.mfa_token)
    if not user.mfa_enabled or not auth_svc.verify_totp(user.mfa_secret, payload.code):
        await auth_svc.record_failure(ip, user.email)
        raise HTTPException(status_code=401, detail="Invalid MFA code")
    await auth_svc.clear_failures(ip, user.email)
    return auth_svc.token_pair(user)


@router.post("/mfa/setup-session", response_model=MfaSetupResponse)
async def mfa_setup_session(
    payload: MfaSetupSessionRequest,
    db: AsyncSession = Depends(get_db),
) -> MfaSetupResponse:
    """Enrol a user for MFA during a login in progress (enforced-MFA flow)."""
    user = await auth_svc.resolve_mfa_session(db, payload.mfa_token)
    if user.role == "demo":
        raise HTTPException(status_code=403, detail="Demo accounts cannot set up MFA")
    resp = auth_svc.build_mfa_setup(user)
    await db.commit()
    return resp


@router.post("/mfa/complete-setup", response_model=TokenPair)
async def mfa_complete_setup(
    payload: MfaVerifyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    """Activate MFA after a login-in-progress setup session, completing login."""
    ip = auth_svc.client_ip(request)
    await auth_svc.check_rate_limit(ip)
    user = await auth_svc.resolve_mfa_session(db, payload.mfa_token)
    if user.role == "demo":
        raise HTTPException(status_code=403, detail="Demo accounts cannot set up MFA")
    if not user.mfa_secret or not auth_svc.verify_totp(user.mfa_secret, payload.code):
        raise HTTPException(status_code=400, detail="Invalid MFA code")
    await auth_svc.clear_failures(ip, user.email)
    user.mfa_enabled = True
    await db.commit()
    await mail.send_security_alert(
        user.email, user.display_name,
        "Two-factor authentication (MFA) was enabled on your account.",
    )
    return auth_svc.token_pair(user)


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenPair:
    """Exchange a refresh token for a fresh access+refresh pair.

    Refresh tokens rotate on every use: the presented token is immediately
    revoked (recorded in the denylist), so a stolen/replayed token is rejected
    and each device keeps only the latest pair. A bumped token_version
    (logout, password change) also rejects every older token outright.
    """
    data = _decode_token(payload.refresh_token)
    if not data or data.get("type") != "refresh" or not data.get("jti"):
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user = await db.get(User, data.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if data.get("ver", 0) != user.token_version:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    jti = data["jti"]
    if await db.get(RevokedRefreshToken, jti):
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    try:
        db.add(
            RevokedRefreshToken(
                jti=jti,
                expires_at=datetime.fromtimestamp(data["exp"], tz=timezone.utc),
            )
        )
        await _prune_revoked_refresh(db)
        await db.commit()
    except IntegrityError:
        # Concurrent replay of the same token: the other request rotated it first.
        await db.rollback()
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    return auth_svc.token_pair(user)


@router.post("/logout", status_code=200)
async def logout(payload: RefreshRequest, db: AsyncSession = Depends(get_db)) -> dict:
    """Revoke the account's sessions by bumping its token_version.

    All outstanding access + refresh tokens for this user are invalidated
    immediately (stolen tokens included). Logs the user out everywhere.
    """
    data = _decode_token(payload.refresh_token)
    if not data or data.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user = await db.get(User, data.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if data.get("ver", 0) != user.token_version:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user.token_version += 1
    await db.commit()
    return {"message": "Logged out — all sessions were revoked"}


@router.get("/config")
async def auth_config() -> dict:
    """Public client config (no auth). Frontend hides self-signup when disabled.

    `app_version` lets the mobile app detect when it is behind the server and
    prompt the user to update (see autobrain-mobile).
    """
    return {
        "signup_enabled": settings.SELF_SIGNUP_ENABLED,
        "mfa_enforced": settings.MFA_ENFORCED,
        "license_enabled": settings.LICENSE_ENABLED,
        "app_version": settings.APP_VERSION,
    }


@router.get("/me", response_model=UserWithVehicleCount)
async def me(
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserWithVehicleCount:
    from app.models.vehicle import Vehicle
    from app.services import iap

    count = await db.scalar(
        select(func.count()).select_from(Vehicle).where(Vehicle.user_id == current.id)
    )
    count = count or 0
    remaining = max(current.max_vehicles - count, 0)
    from app.services import billing as billing_svc

    # Verify-on-refresh (AUT-617): re-validate the stored store purchase token
    # so renewals/refunds propagate without webhooks. Never throws — transient
    # store failures keep the cached entitlement.
    if iap.enabled() and current.iap_purchase_token:
        try:
            await iap.refresh_entitlement(db, current)
        except Exception:
            logger.exception("auth_me_iap_refresh_error")
            await db.rollback()

    iap_state = billing_svc.iap_status(current)
    subscription_status = current.stripe_subscription_status
    if iap_state == "active" and subscription_status not in billing_svc.ACTIVE_STATUSES:
        # An active store entitlement is a paid subscription: reflect it even
        # when no Stripe subscription exists.
        subscription_status = "active"

    return UserWithVehicleCount.model_validate(
        {
            "id": current.id,
            "email": current.email,
            "display_name": current.display_name,
            "role": current.role,
            "is_active": current.is_active,
            "mfa_enabled": current.mfa_enabled,
            "max_vehicles": current.max_vehicles,
            "free_account": current.free_account,
            "obd_enabled": current.obd_enabled,
            "obd_auto_connect": current.obd_auto_connect,
            "vehicle_count": count,
            "vehicles_remaining": remaining,
            "plan": billing_svc.plan_for_user(current),
            "subscription_status": subscription_status,
            "license_status": billing_svc.license_status(current),
            "iap_status": iap_state,
            "trial_days": billing_svc.TRIAL_PERIOD_DAYS if not current.has_had_trial else 0,
            "trial_available": not current.has_had_trial,
        }
    )


@router.patch("/settings", response_model=UserOut)
async def update_settings(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> User:
    """Self-service account settings. Account tier (free/paid) and OBD access
    are admin-managed; users may only toggle OBD Bluetooth auto-connect."""
    allowed = {"obd_auto_connect"}
    for key, value in payload.items():
        if key not in allowed or not isinstance(value, bool):
            continue
        setattr(user, key, value)
    await db.commit()
    await db.refresh(user)
    return user


# --- MFA management (self-service, authenticated) ---
@router.get("/mfa/setup", response_model=MfaSetupResponse)
async def mfa_setup(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MfaSetupResponse:
    resp = auth_svc.build_mfa_setup(user)
    # Persist the pending secret; enable() verifies then activates it.
    await db.commit()
    return resp


@router.post("/mfa/enable", response_model=UserOut)
async def mfa_enable(
    payload: MfaCodeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> User:
    if not user.mfa_secret or not auth_svc.verify_totp(user.mfa_secret, payload.code):
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
    if not user.mfa_enabled or not auth_svc.verify_totp(user.mfa_secret, payload.code):
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
    data = _decode_token(payload.token)
    if not data or data.get("type") not in ("password_reset", "invite"):
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    user = await db.get(User, data.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    user.hashed_password = hash_password(payload.new_password)
    if data.get("type") == "invite":
        user.pending = False  # invited user completed registration by setting a password
    # Password change revokes every outstanding access + refresh token.
    user.token_version += 1
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
    if not payload.send_invite and not payload.password:
        raise HTTPException(status_code=422, detail="Password required (or enable email invite)")
    hashed = hash_password(payload.password) if payload.password else auth_svc.random_password()
    user = User(
        email=payload.email.lower(),
        display_name=payload.display_name,
        hashed_password=hashed,
        role=payload.role,
        max_vehicles=payload.max_vehicles,
        pending=payload.send_invite,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    if payload.send_invite:
        token = create_invite_token(user.id, days=7)
        await mail.send_account_invite(user.email, user.display_name, token, settings.APP_BASE_URL, expiry_days=7)
    else:
        await mail.send_welcome(user.email, user.display_name, settings.APP_BASE_URL)
    return auth_svc.token_pair(user)


# --- public self-service signup (hosted Free tier) ---
@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def public_signup(
    payload: SignupRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a Free-tier account with display name + email only. A setup link
    is emailed to finish activation (password + MFA). Enabled via
    SELF_SIGNUP_ENABLED (hosted instance); self-hosted servers keep
    admin-only provisioning."""
    if not settings.SELF_SIGNUP_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="Self-service signup is disabled on this server. Ask your administrator for an account.",
        )
    existing = await db.scalar(select(User).where(User.email == payload.email.lower()))
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    name_taken = await db.scalar(
        select(User).where(func.lower(User.display_name) == payload.display_name.lower())
    )
    if name_taken:
        raise HTTPException(status_code=409, detail="Display name already in use")
    user = User(
        email=payload.email.lower(),
        display_name=payload.display_name,
        hashed_password=auth_svc.random_password(),
        role="user",
        max_vehicles=1,
        free_account=True,
        pending=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    token = create_invite_token(user.id, days=7)
    await mail.send_signup_setup(
        user.email, user.display_name, token, settings.APP_BASE_URL, expiry_days=7
    )
    return {
        "message": "Account created — check your email to finish setting it up.",
        "email": user.email,
    }


# --- profile data portability (export / import own data) ---
@router.get("/export")
async def export_profile(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Export the whole account (user + vehicles + all records) as JSON."""
    from app.services.backup import dump_backup, serialize_user

    data = await serialize_user(db, user.id)
    content = dump_backup(data)
    stamp = time.strftime("%Y%m%d")
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="autobrain-profile-{stamp}.json"'},
    )


@router.post("/import")
async def import_profile(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> dict:
    """Restore an exported profile onto the logged-in account.

    Wipes the current user's vehicles + records and replaces them with the
    profile's data. Account identity (email/password) is unchanged.
    """
    from app.services.backup import restore_user_data

    raw = await file.read()
    if len(raw) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large")
    try:
        data = _json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, _json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Not a valid AutoBrain export file")
    if data.get("app") != "autobrain" or data.get("kind") != "profile":
        raise HTTPException(status_code=400, detail="Not an AutoBrain profile export file")
    try:
        await restore_user_data(db, user.id, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"message": "Profile restored — your vehicles and records were replaced"}


# --- helpers ---
def _verify_password(password: str, hashed: str) -> bool:
    from app.core.security import verify_password
    return verify_password(password, hashed)


def _decode_token(token: str) -> dict[str, Any] | None:
    from app.core.security import decode_token
    return decode_token(token)


async def _prune_revoked_refresh(db: AsyncSession) -> None:
    """Drop denylist rows past their token's natural expiry (keeps the table bounded)."""
    await db.execute(
        delete(RevokedRefreshToken).where(
            RevokedRefreshToken.expires_at < datetime.now(timezone.utc)
        )
    )
