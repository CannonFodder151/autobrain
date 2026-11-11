"""API Keys for public developer access (AUT-423).

Each key is an opaque random string (e.g. `abapi_<hex>`) presented as
`X-API-Key` header. The backend stores only a sha256 digest, so a DB leak
cannot be replayed as a live key. Lookup narrows by a short prefix index
before the full digest is compared in constant time.

Keys have scopes (read:vehicles, write:services, etc.) and per-key rate limits.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.user import User


def _uuid() -> str:
    return str(uuid.uuid4())


class ApiKey(Base):
    """Developer API key for programmatic access."""

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    # Key lookup narrows by this short prefix index (PREFIX + 4 hex chars),
    # then the full hash is compared (see app.services.api_keys).
    api_key_prefix: Mapped[str] = mapped_column(String(14), index=True)
    api_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # JSON array of scopes, e.g. ["read:vehicles", "write:services", "read:fuel"]
    scopes: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    # Per-key rate limit: requests per window (default from settings)
    rate_limit: Mapped[int | None] = mapped_column(nullable=True)
    rate_window_seconds: Mapped[int | None] = mapped_column(nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    embedding: Mapped[list[float] | None] = mapped_column(Text, nullable=True)