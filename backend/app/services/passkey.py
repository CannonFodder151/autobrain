"""WebAuthn passkey service: registration + authentication ceremony logic.

Wraps py_webauthn for deterministic, testable passkey operations. The frontend
calls navigator.credentials.create/get() and posts back the raw results here
for server-side verification.
"""

import secrets
import time
from base64 import urlsafe_b64decode
from typing import List, Tuple

from app.core.logging import get_logger
from app.models.user import User

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Challenge TTL: challenges are valid for 5 minutes (in seconds)
_CHALLENGE_TTL_SECONDS = 300

# In-memory challenge store — keyed by (user_id, ceremony, request_id).
# In production this lives in Redis; here we use a dict for simplicity
# (a single-worker deployment won't outlive this, and we use Redis when
# it's available).
_challenge_store: dict[str, tuple[bytes, float]] = {}


def _b64url_to_bytes(value: str) -> bytes:
    """Decode a base64url-encoded string to bytes (per WebAuthn spec)."""
    remainder = len(value) % 4
    if remainder:
        value += "=" * (4 - remainder)
    return urlsafe_b64decode(value)


def _bytes_to_b64url(value: bytes) -> str:
    """Encode bytes to base64url string (per WebAuthn spec)."""
    import base64
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _gen_request_id() -> str:
    return secrets.token_urlsafe(32)


def _challenge_key(user_id: str, ceremony: str, request_id: str) -> str:
    return f"webauthn:challenge:{ceremony}:{user_id}:{request_id}"


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def build_registration_options(
    user: User,
    rp_id: str,
    rp_name: str,
    user_id_b64: str,
    user_display_name: str,
    challenge_b64: str,
    timeout_ms: int = 60_000,
    attestation: str = "none",
    authenticator_selection: dict | None = None,
    exclude_credential_ids: List[str] | None = None,
) -> Tuple[dict, str]:
    """Generate WebAuthn registration options for the frontend.

    Returns (options_json_dict, request_id).
    The frontend calls navigator.credentials.create(options) and posts
    the result to the complete-registration endpoint.
    """
    import webauthn
    from webauthn.helpers.structs import (
        AttestationConveyancePreference,
        AuthenticatorSelectionCriteria,
        PublicKeyCredentialDescriptor,
    )

    challenge_bytes = _b64url_to_bytes(challenge_b64)
    user_id_bytes = _b64url_to_bytes(user_id_b64)

    # Build exclude list from existing credentials
    exclude_creds: list[PublicKeyCredentialDescriptor] | None = None
    if exclude_credential_ids:
        exclude_creds = []
        for cid_b64 in exclude_credential_ids:
            try:
                exclude_creds.append(
                    PublicKeyCredentialDescriptor(id=_b64url_to_bytes(cid_b64))
                )
            except Exception:
                continue

    # Map attestation string to enum
    attestation_enum = {
        "none": AttestationConveyancePreference.NONE,
        "indirect": AttestationConveyancePreference.INDIRECT,
        "direct": AttestationConveyancePreference.DIRECT,
        
    }.get(attestation, AttestationConveyancePreference.NONE)

    # Parse authenticator selection if provided
    selection: AuthenticatorSelectionCriteria | None = None
    if authenticator_selection:
        selection = AuthenticatorSelectionCriteria(**authenticator_selection)

    options = webauthn.generate_registration_options(
        rp_id=rp_id,
        rp_name=rp_name,
        user_name=user_id_b64,
        user_id=user_id_bytes,
        user_display_name=user_display_name,
        challenge=challenge_bytes,
        timeout=timeout_ms,
        attestation=attestation_enum,
        authenticator_selection=selection,
        exclude_credentials=exclude_creds,
    )

    request_id = _gen_request_id()
    store_key = _challenge_key(user.id, "register", request_id)
    _challenge_store[store_key] = (challenge_bytes, time.time())

    return {
        "rp": {"name": options.rp.name, "id": options.rp.id},
        "user": {
            "id": _bytes_to_b64url(options.user.id),
            "name": options.user.name,
            "displayName": options.user.display_name,
        },
        "challenge": _bytes_to_b64url(options.challenge),
        "pubKeyCredParams": [
            {"alg": p.alg, "type": p.type} for p in options.pub_key_cred_params
        ],
        "timeout": options.timeout,
        "excludeCredentials": [
            {"id": _bytes_to_b64url(c.id), "type": c.type}
            for c in (options.exclude_credentials or [])
        ],
        "attestation": options.attestation.value,
    }, request_id


def verify_registration(
    user: User,
    request_id: str,
    credential_id_b64: str,
    raw_id_b64: str,
    client_data_json_b64: str,
    attestation_object_b64: str,
    transports: List[str] | None,
    rp_id: str,
    expected_origin: str,
) -> dict:
    """Verify a registration ceremony response and return credential data.

    Raises ValueError on any validation failure.
    Returns dict with: credential_id, credential_public_key, sign_count,
    credential_backed_up, credential_device_type, user_verified.
    """
    import webauthn
    from webauthn.helpers.structs import (
        AuthenticatorAttestationResponse,
        RegistrationCredential,
    )

    store_key = _challenge_key(user.id, "register", request_id)
    if store_key not in _challenge_store:
        raise ValueError("Registration session not found or expired")
    expected_challenge_bytes, created_at = _challenge_store.pop(store_key)

    if time.time() - created_at > _CHALLENGE_TTL_SECONDS:
        raise ValueError("Registration session expired — try again")

    try:
        credential = RegistrationCredential(
            id=credential_id_b64,
            raw_id=_b64url_to_bytes(raw_id_b64),
            type="public-key",
            response=AuthenticatorAttestationResponse(
                client_data_json=_b64url_to_bytes(client_data_json_b64),
                attestation_object=_b64url_to_bytes(attestation_object_b64),
                transports=transports,
            ),
        )
        result = webauthn.verify_registration_response(
            credential=credential,
            expected_challenge=expected_challenge_bytes,
            expected_rp_id=rp_id,
            expected_origin=expected_origin,
            require_user_presence=True,
            require_user_verification=False,
        )
    except Exception as exc:
        logger.warning("webauthn_registration_verification_failed", error=str(exc))
        raise ValueError(f"Registration verification failed: {exc}") from exc

    return {
        "credential_id": _bytes_to_b64url(result.credential_id),
        "credential_public_key": _bytes_to_b64url(result.credential_public_key),
        "sign_count": result.sign_count,
        "credential_backed_up": result.credential_backed_up,
        "credential_device_type": result.credential_device_type.value
        if hasattr(result.credential_device_type, "value")
        else str(result.credential_device_type),
        "user_verified": result.user_verified,
    }


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def build_authentication_options(
    user_id: str,
    rp_id: str,
    challenge_b64: str,
    allow_credentials: List[dict],
    timeout_ms: int = 60_000,
    user_verification: str = "preferred",
) -> Tuple[dict, str]:
    """Generate WebAuthn authentication options for the frontend.

    Returns (options_json_dict, request_id).
    """
    import webauthn
    from webauthn.helpers.structs import PublicKeyCredentialDescriptor

    challenge_bytes = _b64url_to_bytes(challenge_b64)

    # Build allow_credentials from dicts
    allow_list: list[PublicKeyCredentialDescriptor] = []
    for cred in allow_credentials:
        try:
            desc = PublicKeyCredentialDescriptor(
                id=_b64url_to_bytes(cred["id"]),
                type="public-key",
            )
            allow_list.append(desc)
        except Exception:
            continue

    uv_enum = {
        "required": "required",
        "preferred": "preferred",
        "discouraged": "discouraged",
    }.get(user_verification, "preferred")

    # Use PREFERRED by default
    from webauthn.helpers.structs import UserVerificationRequirement
    uv = UserVerificationRequirement(uv_enum)

    request_id = _gen_request_id()

    options = webauthn.generate_authentication_options(
        rp_id=rp_id,
        challenge=challenge_bytes,
        timeout=timeout_ms,
        allow_credentials=allow_list if allow_list else None,
        user_verification=uv,
    )

    store_key = _challenge_key(user_id, "auth", request_id)
    _challenge_store[store_key] = (challenge_bytes, time.time())

    return {
        "challenge": _bytes_to_b64url(options.challenge),
        "timeout": options.timeout,
        "rpId": options.rp_id,
        "allowCredentials": [
            {"id": _bytes_to_b64url(c.id), "type": c.type}
            for c in (options.allow_credentials or [])
        ],
        "userVerification": options.user_verification.value,
    }, request_id


def verify_authentication(
    user_id: str,
    request_id: str,
    credential_id_b64: str,
    raw_id_b64: str,
    client_data_json_b64: str,
    authenticator_data_b64: str,
    signature_b64: str,
    user_handle_b64: str | None,
    expected_credential_public_key_b64: str,
    expected_sign_count: int,
    rp_id: str,
    expected_origin: str,
) -> dict:
    """Verify an authentication ceremony response.

    Raises ValueError on any validation failure.
    Returns dict with: new_sign_count, user_verified, credential_backed_up.
    """
    import webauthn
    from webauthn.helpers.structs import (
        AuthenticationCredential,
        AuthenticatorAssertionResponse,
    )

    store_key = _challenge_key(user_id, "auth", request_id)
    if store_key not in _challenge_store:
        raise ValueError("Authentication session not found or expired")
    expected_challenge_bytes, created_at = _challenge_store.pop(store_key)

    if time.time() - created_at > _CHALLENGE_TTL_SECONDS:
        raise ValueError("Authentication session expired — try again")

    try:
        credential = AuthenticationCredential(
            id=credential_id_b64,
            raw_id=_b64url_to_bytes(raw_id_b64),
            type="public-key",
            response=AuthenticatorAssertionResponse(
                client_data_json=_b64url_to_bytes(client_data_json_b64),
                authenticator_data=_b64url_to_bytes(authenticator_data_b64),
                signature=_b64url_to_bytes(signature_b64),
                user_handle=_b64url_to_bytes(user_handle_b64) if user_handle_b64 else None,
            ),
        )
        result = webauthn.verify_authentication_response(
            credential=credential,
            expected_challenge=expected_challenge_bytes,
            expected_rp_id=rp_id,
            expected_origin=expected_origin,
            credential_public_key=_b64url_to_bytes(expected_credential_public_key_b64),
            credential_current_sign_count=expected_sign_count,
            require_user_verification=False,
        )
    except Exception as exc:
        logger.warning("webauthn_auth_verification_failed", error=str(exc))
        raise ValueError(f"Authentication verification failed: {exc}") from exc

    return {
        "new_sign_count": result.new_sign_count,
        "user_verified": result.user_verified,
        "credential_backed_up": result.credential_backed_up,
    }