"""WebAuthn passkey schemas."""

from base64 import urlsafe_b64decode
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field, validator


def _b64url_to_bytes(value: str) -> bytes:
    """Decode a base64url-encoded string to bytes (per WebAuthn spec)."""
    # Add padding if needed
    remainder = len(value) % 4
    if remainder:
        value += "=" * (4 - remainder)
    return urlsafe_b64decode(value)


def _bytes_to_b64url(value: bytes) -> str:
    """Encode bytes to base64url string (per WebAuthn spec)."""
    import base64
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


# ---------------------------------------------------------------------------
# Core passkey schemas
# ---------------------------------------------------------------------------


class PasskeyCredentialOut(BaseModel):
    """Returned passkey info (excluding raw crypto material)."""

    id: str
    user_id: str
    credential_id: str  # base64url
    label: str = ""
    device_type: str = "unknown"
    transports: str = ""
    created_at: datetime
    last_used_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PasskeyRegistrationBegin(BaseModel):
    """Request body for starting a passkey registration ceremony.

    The frontend uses this to generate WebAuthn options via
    `navigator.credentials.create()`.
    """

    rp_id: str = Field(..., description="Relying Party identifier (e.g. app domain)")
    rp_name: str = Field(..., description="Human-readable RP name")
    user_display_name: str = Field(..., min_length=1, max_length=120)
    user_id: str = Field(..., min_length=1, max_length=128)  # base64url-encoded
    challenge: str = Field(..., min_length=16, max_length=64)  # base64url-encoded bytes
    timeout: int = Field(default=60000, ge=1000, le=900000)  # ms
    attestation: str = Field(default="none", pattern="^(none|indirect|direct|user preferred)$")
    authenticator_selection: Optional[dict] = Field(default=None)
    exclude_credential_ids: List[str] = Field(default_factory=list)  # base64url

    @validator("challenge")
    def _challenge_must_be_valid_b64url(cls, v: str) -> str:
        try:
            _b64url_to_bytes(v)
        except Exception as exc:
            raise ValueError("challenge must be valid base64url") from exc
        return v


class PasskeyRegistrationComplete(BaseModel):
    """Request body for completing a passkey registration ceremony.

    The frontend posts the authenticator's response to navigator.credentials.create().
    """

    credential_public_key: str = Field(..., description="COSE public key bytes (base64url)")
    credential_attestation: str = Field(
        ..., description="Attestation object (base64url or stringified JSON)"
    )
    credential_client_data_json: str = Field(
        ..., description="Client data JSON (base64url or stringified JSON)"
    )
    credential_device_type: str = Field(
        ...,
        pattern="^(platform|cross-platform|unknown)$",
    )
    credential_attestation_transport: Optional[str] = Field(
        default=None,
        pattern="^(none|usb|nfc|ble|internal)$",
    )

    @validator("credential_public_key", "credential_attestation", "credential_client_data_json")
    def _b64url_or_json(cls, v: str) -> str:
        """Accept either base64url or a JSON string."""
        # Try base64url decode first
        try:
            _b64url_to_bytes(v)
            return v  # valid base64url
        except Exception:
            pass
        # Try JSON parse
        try:
            import json as _json
            _json.loads(v)
            return v  # valid JSON
        except Exception:
            pass
        raise ValueError("credential data must be base64url or stringified JSON")


class PasskeyAuthenticationBegin(BaseModel):
    """Request body for starting a passkey authentication ceremony.

    The frontend uses this to generate WebAuthn options via
    `navigator.credentials.get()`.
    """

    rp_id: str = Field(..., description="Relying Party identifier (e.g. app domain)")
    challenge: str = Field(..., min_length=16, max_length=64)  # base64url-encoded bytes
    allow_credentials: List[dict] = Field(
        ...,
        description="List of credential descriptors from registered passkeys. "
        "Each entry has: id (base64url), type (public-key), transports (optional).",
    )
    timeout: int = Field(default=60000, ge=1000, le=900000)  # ms
    user_verification: str = Field(
        default="preferred",
        pattern="^(required|preferred|discouraged)$",
    )

    @validator("challenge")
    def _challenge_must_be_valid_b64url(cls, v: str) -> str:
        try:
            _b64url_to_bytes(v)
        except Exception as exc:
            raise ValueError("challenge must be valid base64url") from exc
        return v


class PasskeyAuthenticationComplete(BaseModel):
    """Request body for completing a passkey authentication ceremony.

    The frontend posts the authenticator's response to navigator.credentials.get().
    """

    credential_id: str = Field(..., description="Credential ID (base64url) matching a stored passkey")
    credential_response: dict = Field(
        ...,
        description="Full navigator.credentials.get() response object "
        "(stringified JSON or dict with: authenticatorData, clientDataJSON, signature, unsignedPermission)",
    )

    @staticmethod
    def _normalize_credential_response(value: Any) -> dict:
        """Ensure credential_response is a dict."""
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            import json as _json
            return _json.loads(value)
        raise ValueError("credential_response must be a dict or stringified JSON")

    @validator("credential_response")
    def _credential_response_must_be_dict(cls, v: Any) -> dict:
        return cls._normalize_credential_response(v)


class PasskeyListFilter(BaseModel):
    """Query params for listing a user's passkeys."""

    pass


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class PasskeyRegistrationSuccess(BaseModel):
    """Success response after completing registration."""

    success: bool = True
    credential_id: str  # base64url for client reference
    user_verified: bool


class PasskeyAuthenticationSuccess(BaseModel):
    """Success response after completing authentication."""

    success: bool = True
    user_verified: bool
    sign_count: int  # new counter value from authenticator


class PasskeyListResponse(BaseModel):
    """List of a user's registered passkeys."""

    passkeys: list[PasskeyCredentialOut]


# ---------------------------------------------------------------------------
# API error schemas
# ---------------------------------------------------------------------------


class PasskeyError(BaseModel):
    """Standard passkey API error response."""

    error: str
    detail: str


class PasskeyRegistrationBeginResponse(BaseModel):
    """Response wrapping WebAuthn registration options for the frontend."""

    options: dict  # generated by py_webauthn.generate_registration_options
    request_id: str  # opaque correlate for the ceremony


class PasskeyAuthenticationBeginResponse(BaseModel):
    """Response wrapping WebAuthn authentication options for the frontend."""

    options: dict  # generated by py_webauthn.generate_authentication_options
    request_id: str  # opaque correlate for the ceremony