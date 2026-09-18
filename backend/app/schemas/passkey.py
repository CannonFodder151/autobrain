"""WebAuthn passkey schemas."""

from base64 import urlsafe_b64decode
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


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
    navigator.credentials.create().
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

    @field_validator("challenge")
    @classmethod
    def _challenge_must_be_valid_b64url(cls, v: str) -> str:
        try:
            _b64url_to_bytes(v)
        except Exception as exc:
            raise ValueError("challenge must be valid base64url") from exc
        return v


class PasskeyRegistrationComplete(BaseModel):
    """Request body for completing a passkey registration ceremony.

    The frontend posts the authenticator response to navigator.credentials.create().
    The credential object structure from navigator.credentials.create():
    - id: base64url string (credential ID)
    - rawId: base64url string (raw credential ID bytes)
    - response: { clientDataJSON, attestationObject, transports[] }
    - type: "public-key"
    """

    credential: dict = Field(
        ...,
        description="Full navigator.credentials.create() response object "
        "(dict with: id, rawId, response {clientDataJSON, attestationObject, transports}, type)",
    )
    request_id: str = Field(
        ..., min_length=1, max_length=128,
        description="Request ID from /register/begin response",
    )

    @field_validator("credential")
    @classmethod
    def _credential_must_have_required_fields(cls, v: dict) -> dict:
        if not isinstance(v, dict):
            raise ValueError("credential must be a dict")
        required_keys = {"id", "rawId", "response", "type"}
        missing = required_keys - set(v.keys())
        if missing:
            raise ValueError(f"credential missing required fields: {missing}")
        if v.get("type") != "public-key":
            raise ValueError("credential type must be 'public-key'")
        response = v.get("response")
        if not isinstance(response, dict):
            raise ValueError("credential.response must be a dict")
        r_keys = {"clientDataJSON", "attestationObject"}
        if not r_keys.issubset(set(response.keys())):
            raise ValueError(f"credential.response missing fields: {r_keys - set(response.keys())}")
        return v


class PasskeyAuthenticationBegin(BaseModel):
    """Request body for starting a passkey authentication ceremony.

    The frontend uses this to generate WebAuthn options via
    navigator.credentials.get().
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

    @field_validator("challenge")
    @classmethod
    def _challenge_must_be_valid_b64url(cls, v: str) -> str:
        try:
            _b64url_to_bytes(v)
        except Exception as exc:
            raise ValueError("challenge must be valid base64url") from exc
        return v


class PasskeyAuthenticationComplete(BaseModel):
    """Request body for completing a passkey authentication ceremony.

    The frontend posts the authenticator response to navigator.credentials.get().
    The credential object structure from navigator.credentials.get():
    - id: base64url string (credential ID)
    - rawId: base64url string (raw credential ID bytes)
    - response: { clientDataJSON, authenticatorData, signature, userHandle }
    - type: "public-key"
    """

    credential: dict = Field(
        ...,
        description="Full navigator.credentials.get() response object "
        "(dict with: id, rawId, response {clientDataJSON, authenticatorData, signature, userHandle}, type)",
    )
    request_id: str = Field(
        ..., min_length=1, max_length=128,
        description="Request ID from /authenticate/begin response",
    )

    @field_validator("credential")
    @classmethod
    def _credential_must_have_required_fields(cls, v: dict) -> dict:
        if not isinstance(v, dict):
            raise ValueError("credential must be a dict")
        required_keys = {"id", "rawId", "response", "type"}
        missing = required_keys - set(v.keys())
        if missing:
            raise ValueError(f"credential missing required fields: {missing}")
        if v.get("type") != "public-key":
            raise ValueError("credential type must be 'public-key'")
        response = v.get("response")
        if not isinstance(response, dict):
            raise ValueError("credential.response must be a dict")
        r_keys = {"clientDataJSON", "authenticatorData", "signature"}
        if not r_keys.issubset(set(response.keys())):
            raise ValueError(f"credential.response missing fields: {r_keys - set(response.keys())}")
        return v


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
