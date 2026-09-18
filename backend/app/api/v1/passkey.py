"""WebAuthn passkey API routes.

Endpoints:
- POST /auth/passkey/register/begin   — start passkey registration (authenticated)
- POST /auth/passkey/register/complete — complete registration, store credential
- POST /auth/passkey/authenticate/begin — start passkey authentication (public)
- POST /auth/passkey/authenticate/complete — complete auth, issue tokens
- GET  /auth/passkey/list             — list user's passkeys (authenticated)
- DELETE /auth/passkey/{credential_id} — delete a passkey (authenticated)
"""

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_write
from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token
from app.models.passkey import PasskeyCredential
from app.models.user import User
from app.schemas.passkey import (
    PasskeyAuthenticationBegin,
    PasskeyAuthenticationBeginResponse,
    PasskeyAuthenticationComplete,
    PasskeyAuthenticationSuccess,
    PasskeyCredentialOut,
    PasskeyError,
    PasskeyListResponse,
    PasskeyRegistrationBegin,
    PasskeyRegistrationBeginResponse,
    PasskeyRegistrationComplete,
    PasskeyRegistrationSuccess,
)
from app.services import passkey as passkey_svc

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/passkey", tags=["auth"])


def _generate_challenge() -> str:
    """Generate a cryptographically random challenge (base64url)."""
    from base64 import urlsafe_b64encode
    import secrets
    return urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()


def _get_expected_origin(request: Request) -> str:
    """Get expected origin from request headers or APP_BASE_URL."""
    origin = request.headers.get("origin")
    if not origin:
        return settings.APP_BASE_URL.rstrip("/")
    return origin


def _get_expected_rp_id(request: Request) -> str:
    """Get expected RP ID (hostname from origin or APP_BASE_URL)."""
    from urllib.parse import urlparse
    origin = _get_expected_origin(request)
    parsed = urlparse(origin)
    return parsed.hostname or "localhost"


# ---------------------------------------------------------------------------
# Registration (requires authenticated user)
# ---------------------------------------------------------------------------


@router.post(
    "/register/begin",
    response_model=PasskeyRegistrationBeginResponse,
    responses={400: {"model": PasskeyError}, 401: {"model": PasskeyError}},
)
async def passkey_register_begin(
    request: Request,
    payload: PasskeyRegistrationBegin,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PasskeyRegistrationBeginResponse:
    """Start a passkey registration ceremony for the authenticated user.

    Returns WebAuthn PublicKeyCredentialCreationOptions for the frontend
    to pass to navigator.credentials.create().
    """
    expected_rp_id = _get_expected_rp_id(request)
    if payload.rp_id != expected_rp_id:
        raise HTTPException(
            status_code=400,
            detail=f"RP ID mismatch: expected {expected_rp_id}, got {payload.rp_id}",
        )

    existing_creds = await db.scalars(
        select(PasskeyCredential.credential_id).where(
            PasskeyCredential.user_id == user.id
        )
    )
    exclude_ids = list(existing_creds.all())

    from base64 import urlsafe_b64encode
    challenge_b64 = _generate_challenge()

    options, request_id = passkey_svc.build_registration_options(
        user=user,
        rp_id=payload.rp_id,
        rp_name=payload.rp_name,
        user_id_b64=urlsafe_b64encode(user.id.encode()).rstrip(b"=").decode(),
        user_display_name=payload.user_display_name,
        challenge_b64=challenge_b64,
        timeout_ms=payload.timeout,
        attestation=payload.attestation,
        authenticator_selection=payload.authenticator_selection,
        exclude_credential_ids=exclude_ids,
    )

    return PasskeyRegistrationBeginResponse(options=options, request_id=request_id)


@router.post(
    "/register/complete",
    response_model=PasskeyRegistrationSuccess,
    responses={400: {"model": PasskeyError}, 401: {"model": PasskeyError}},
)
async def passkey_register_complete(
    request: Request,
    payload: PasskeyRegistrationComplete,
    request_id: str = Query(..., description="Request ID from /register/begin"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PasskeyRegistrationSuccess:
    """Complete a passkey registration ceremony.

    Verifies the authenticator response and stores the credential.
    """
    expected_rp_id = _get_expected_rp_id(request)
    expected_origin = _get_expected_origin(request)

    try:
        result = passkey_svc.verify_registration(
            user=user,
            request_id=request_id,
            credential_id_b64=payload.credential_id,
            attestation_object_b64=payload.attestation_object,
            client_data_json_b64=payload.client_data_json,
            rp_id=expected_rp_id,
            expected_origin=expected_origin,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    credential = PasskeyCredential(
        user_id=user.id,
        credential_id=result["credential_id"],
        public_key=result["credential_public_key"],
        sign_count=result["sign_count"],
        device_type=result["credential_device_type"],
        label=f"Passkey {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}",
    )
    db.add(credential)
    await db.commit()
    await db.refresh(credential)

    return PasskeyRegistrationSuccess(
        success=True,
        credential_id=result["credential_id"],
        user_verified=result["user_verified"],
    )


# ---------------------------------------------------------------------------
# Authentication (public — no auth required)
# ---------------------------------------------------------------------------


@router.post(
    "/authenticate/begin",
    response_model=PasskeyAuthenticationBeginResponse,
    responses={400: {"model": PasskeyError}, 404: {"model": PasskeyError}},
)
async def passkey_authenticate_begin(
    request: Request,
    payload: PasskeyAuthenticationBegin,
    db: AsyncSession = Depends(get_db),
) -> PasskeyAuthenticationBeginResponse:
    """Start a passkey authentication ceremony.

    Looks up the user by email (from query param) and returns WebAuthn
    options for their registered passkeys. This endpoint is PUBLIC.
    """
    email = request.query_params.get("email")
    user_id = request.query_params.get("user_id")

    if not user_id and not email:
        raise HTTPException(
            status_code=400,
            detail="Provide user_id or email query parameter",
        )

    if email:
        user = await db.scalar(select(User).where(User.email == email.lower()))
    else:
        user = await db.get(User, user_id)

    if not user or not user.is_active:
        options, request_id = passkey_svc.build_authentication_options(
            user_id="unknown",
            rp_id=payload.rp_id,
            challenge_b64=_generate_challenge(),
            allow_credentials=[],
            timeout_ms=payload.timeout,
            user_verification=payload.user_verification,
        )
        return PasskeyAuthenticationBeginResponse(options=options, request_id=request_id)

    creds = await db.scalars(
        select(PasskeyCredential).where(PasskeyCredential.user_id == user.id)
    )
    allow_list = [
        {
            "id": c.credential_id,
            "type": "public-key",
            "transports": c.transports.split(",") if c.transports else [],
        }
        for c in creds.all()
    ]

    options, request_id = passkey_svc.build_authentication_options(
        user_id=user.id,
        rp_id=payload.rp_id,
        challenge_b64=_generate_challenge(),
        allow_credentials=allow_list,
        timeout_ms=payload.timeout,
        user_verification=payload.user_verification,
    )

    return PasskeyAuthenticationBeginResponse(options=options, request_id=request_id)


@router.post(
    "/authenticate/complete",
    response_model=PasskeyAuthenticationSuccess,
    responses={400: {"model": PasskeyError}, 401: {"model": PasskeyError}},
)
async def passkey_authenticate_complete(
    request: Request,
    payload: PasskeyAuthenticationComplete,
    request_id: str = Query(..., description="Request ID from /authenticate/begin"),
    db: AsyncSession = Depends(get_db),
) -> PasskeyAuthenticationSuccess:
    """Complete a passkey authentication ceremony.

    Verifies the assertion, updates sign_count, issues JWT tokens.
    Returns the full TokenPair so the frontend can persist auth.
    """
    expected_rp_id = _get_expected_rp_id(request)
    expected_origin = _get_expected_origin(request)

    credential = await db.scalar(
        select(PasskeyCredential).where(
            PasskeyCredential.credential_id == payload.credential_id
        )
    )
    if not credential:
        raise HTTPException(status_code=401, detail="Passkey not found")

    user = await db.get(User, credential.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Account not found or disabled")

    try:
        result = passkey_svc.verify_authentication(
            user_id=user.id,
            request_id=request_id,
            credential_id_b64=payload.credential_id,
            authenticator_data_b64=payload.authenticator_data,
            client_data_json_b64=payload.client_data_json,
            signature_b64=payload.signature,
            user_handle_b64=payload.user_handle,
            expected_credential_public_key_b64=credential.public_key,
            expected_sign_count=credential.sign_count,
            rp_id=expected_rp_id,
            expected_origin=expected_origin,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    credential.sign_count = result["new_sign_count"]
    credential.last_used_at = datetime.now(timezone.utc)
    await db.commit()

    access_token = create_access_token(user.id, token_version=user.token_version)
    refresh_token = create_refresh_token(user.id, token_version=user.token_version)

    return PasskeyAuthenticationSuccess(
        success=True,
        user_verified=result["user_verified"],
        sign_count=result["new_sign_count"],
        access_token=access_token,
        refresh_token=refresh_token,
        user={
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "is_active": user.is_active,
            "mfa_enabled": user.mfa_enabled,
            "max_vehicles": user.max_vehicles,
            "free_account": user.free_account,
            "obd_enabled": user.obd_enabled,
            "obd_auto_connect": user.obd_auto_connect,
        },
    )


# ---------------------------------------------------------------------------
# Management (authenticated)
# ---------------------------------------------------------------------------


@router.get("/list", response_model=PasskeyListResponse)
async def passkey_list(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PasskeyListResponse:
    """List all passkeys registered to the current user."""
    creds = await db.scalars(
        select(PasskeyCredential).where(PasskeyCredential.user_id == user.id)
    )
    return PasskeyListResponse(
        passkeys=[
            PasskeyCredentialOut(
                id=c.id,
                user_id=c.user_id,
                credential_id=c.credential_id,
                label=c.label,
                device_type=c.device_type,
                transports=c.transports,
                created_at=c.created_at,
                last_used_at=c.last_used_at,
            )
            for c in creds.all()
        ]
    )


@router.delete("/{credential_id}", status_code=status.HTTP_200_OK)
async def passkey_delete(
    credential_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> dict:
    """Delete a passkey credential."""
    credential = await db.scalar(
        select(PasskeyCredential).where(
            PasskeyCredential.credential_id == credential_id,
            PasskeyCredential.user_id == user.id,
        )
    )
    if not credential:
        raise HTTPException(status_code=404, detail="Passkey not found")

    await db.delete(credential)
    await db.commit()
    return {"message": "Passkey deleted"}
