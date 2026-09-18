"""WebAuthn passkey credential model."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class PasskeyCredential(Base):
    """Stored WebAuthn credential for passwordless authentication.

    Each row maps one authenticator (device/platform key) to a user account.
    The credential_id and public_key are the raw bytes from the registration
    ceremony (base64url-encoded in transit, stored as text for portability).
    The sign_count is incremented on each successful authentication to detect
    cloned authenticators (replay protection).
    """

    __tablename__ = "passkey_credentials"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    # WebAuthn credential identifier (base64url-encoded raw bytes). Unique per
    # user; the same authenticator cannot register twice.
    credential_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    # COSE public key (base64url-encoded raw bytes)
    public_key: Mapped[str] = mapped_column(Text, nullable=False)
    # Monotonic counter from the authenticator — incremented on each auth to
    # detect cloned authenticators.
    sign_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Human-readable label (e.g. "Chrome on MacBook", "YubiKey 5C")
    label: Mapped[str] = mapped_column(String(120), default="")
    # Authenticator type: "platform" (built-in) or "cross-platform" (roaming)
    device_type: Mapped[str] = mapped_column(String(20), default="unknown")
    # Comma-separated transports hint for the client (usb, nfc, ble, internal)
    transports: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
