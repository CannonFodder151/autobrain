"""WebAuthn passkey schemas."""

from base64 import urlsafe_b64decode
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field, validator


def _b64url_to_bytes(value: str) -> bytes:
    remainder = len(value) % 4
    if remainder:
        value += "=" * (4 - remainder)
    return urlsafe_b64decode(value)


def _bytes_to_b64url(value: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


# ---------------------------------------------------------------------------
# Core passkey schemas
# ---------------------------------------------------------------------------


class PasskeyCredentialOut(BaseModel):
    """Returned passkey info (excluding raw crypto material)."""

    id: str
    user_id: str
    credential_id: str
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
    user_id: str = Field(..., min_length=1, max_length=128)
    challenge: str = Field(..., min_length=16, max_length=64)
    timeout: int = Field(default=60000, ge=1000, le=900000)
    attestation: str = Field(default="none", pattern="^(none|indirect|direct|user preferred)$")
    authenticator_selection: Optional[dict] = Field(default=None)
    exclude_credential_ids: List[str] = Field(default_factory=list)

    @validator("challenge")
    def _challenge_must_be_valid_b64url(cls, v: str) -> str:
        try:
            _b64url_to_bytes(v)
        except Exception as exc:
            raise ValueError("challenge must be valid base64url") from exc
        return v


class PasskeyRegistrationComplete(BaseModel):
    """Request body for completing a passkey registration ceremony.

    Matches navigator.credentials.create() response: id, attestationObject, clientDataJSON.
    All fields are base64url-encoded.
    """

    credential_id: str = Field(..., description="Credential ID (base64url)")
    attestation_object: str = Field(
        ..., description="Attestation object bytes (base64url)"
    )
    client_data_json: str = Field(
        ..., description="Client data JSON bytes (base64url)"
    )

    @validator("credential_id", "attestation_object", "client_data_json")
    def _must_be_valid_b64url(cls, v: str) -> str:
        try:
            _b64url_to_bytes(v)
        except Exception as exc:
            raise ValueError("field must be valid base64url") from exc
        return v


class PasskeyAuthenticationBegin(BaseModel):
    """Request body for starting a passkey authentication ceremony.

    The frontend uses this to generate WebAuthn options via
    `navigator.credentials.get()`.
    """

    rp_id: str = Field(..., description="Relying Party identifier (e.g. app domain)")
    challenge: str = Field(..., min_length=16, max_length=64)
    allow_credentials: List[dict] = Field(
        ...,
        description="List of credential descriptors from registered passkeys. "
        "Each entry has: id (base64url), type (public-key), transports (optional).",
    )
    timeout: int = Field(default=60000, ge=1000, le=900000)
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

    Matches navigator.credentials.get() response: id, authenticatorData, clientDataJSON, signature, userHandle.
    All fields are base64url-encoded.
    """

    credential_id: str = Field(..., description="Credential ID (base64url)")
    authenticator_data: str = Field(..., description="Authenticator data (base64url)")
    client_data_json: str = Field(..., description="Client data JSON (base64url)")
    signature: str = Field(..., description="Signature (base64url)")
    user_handle: Optional[str] = Field(default=None, description="User handle (base64url, optional)")

    @validator("credential_id", "authenticator_data", "client_data_json", "signature")
    def _must_be_valid_b64url(cls, v: str) -> str:
        try:
            _b64url_to_bytes(v)
        except Exception as exc:
            raise ValueError("field must be valid base64url") from exc
        return v


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class PasskeyRegistrationSuccess(BaseModel):
    """Success response after completing registration."""

    success: bool = True
    credential_id: str
    user_verified: bool


class PasskeyAuthenticationSuccess(BaseModel):
    """Success response after completing authentication.

    Returns the full TokenPair so the frontend can persist auth state.
    """

    success: bool = True
    user_verified: bool
    sign_count: int
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict  # UserOut-compatible dict


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

    options: dict
    request_id: str


class PasskeyAuthenticationBeginResponse(BaseModel):
    """Response wrapping WebAuthn authentication options for the frontend."""

    options: dict
    request_id: str