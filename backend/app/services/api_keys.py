"""Public developer API keys (AUT-423).

Keys are opaque 256-bit random strings the developer presents as
`X-API-Key`. The backend stores only a sha256 digest. Lookup narrows
to a short prefix index before the full digest is compared in constant
time.

Scopes control which resources/actions a key can access. Default scopes
grant read-only access to all public resources.
"""

import hashlib
import hmac as _hmac
import json
import secrets
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import ApiKey

PREFIX = "abapi_"
# PREFIX + 8 hex chars = 14 chars total for the indexed prefix
PREFIX_LEN = 14

# Canonical scopes for the public API v1
VALID_SCOPES = frozenset({
    "read:vehicles",
    "read:services",
    "read:fuel",
    "read:diagnostics",
    "read:logbook",
    "read:analytics",
    "write:vehicles",
    "write:services",
    "write:fuel",
    "write:diagnostics",
    "write:logbook",
    "webhooks:read",
    "webhooks:write",
    "admin:keys",
})

DEFAULT_SCOPES = [
    "read:vehicles",
    "read:services",
    "read:fuel",
    "read:diagnostics",
    "read:logbook",
    "read:analytics",
]


def generate_key() -> str:
    """Return a fresh opaque API key, e.g. `abapi_<64 hex chars>`."""
    return PREFIX + secrets.token_hex(32)  # 256 bits


def key_prefix(key: str) -> str:
    return key[:PREFIX_LEN]


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def verify_key(supplied: str, stored_hash: str) -> bool:
    """Constant-time comparison of the supplied key against a stored digest."""
    return _hmac.compare_digest(hash_key(supplied), stored_hash)


def normalize_scopes(scopes: Sequence[str]) -> list[str]:
    """Validate and deduplicate scopes. Returns sorted list."""
    out = []
    seen = set()
    for s in scopes:
        s = s.strip().lower()
        if s and s in VALID_SCOPES and s not in seen:
            out.append(s)
            seen.add(s)
    return sorted(out)


def has_scope(key: ApiKey, required: str) -> bool:
    """Check if the API key has the required scope."""
    try:
        scopes = json.loads(key.scopes or "[]")
    except (json.JSONDecodeError, TypeError):
        return False
    # admin:keys implies all scopes
    if "admin:keys" in scopes:
        return True
    return required in scopes


async def find_key_by_raw(db: AsyncSession, supplied: str) -> ApiKey | None:
    """Look up an active (non-revoked) API key by its raw value."""
    prefix = key_prefix(supplied)
    candidates = list(
        (await db.scalars(select(ApiKey).where(ApiKey.api_key_prefix == prefix))).all()
    )
    for candidate in candidates:
        if candidate.revoked_at is not None:
            continue
        if verify_key(supplied, candidate.api_key_hash):
            return candidate
    return None


async def touch_last_used(db: AsyncSession, key: ApiKey) -> None:
    key.last_used_at = datetime.now(timezone.utc)
    await db.commit()


def serialize_key(key: ApiKey, *, include_secret: bool = False) -> dict:
    """Serialize an ApiKey for API responses. Never exposes the raw key or hash."""
    try:
        scopes = json.loads(key.scopes or "[]")
    except (json.JSONDecodeError, TypeError):
        scopes = []
    data = {
        "id": key.id,
        "label": key.label,
        "prefix": key.api_key_prefix,
        "scopes": scopes,
        "rate_limit": key.rate_limit,
        "rate_window_seconds": key.rate_window_seconds,
        "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
        "created_at": key.created_at.isoformat() if key.created_at else None,
        "revoked_at": key.revoked_at.isoformat() if key.revoked_at else None,
        "is_active": key.revoked_at is None,
    }
    return data
