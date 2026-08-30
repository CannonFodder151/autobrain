"""Revoked refresh tokens (denylist for refresh-token rotation).

On every /auth/refresh the presented refresh token's `jti` is recorded here;
replaying a rotated token is then rejected. Rows are pruned after the
refresh token's natural expiry (see `expires_at`).
"""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class RevokedRefreshToken(Base):
    """A refresh-token jti that has been consumed/rotated and must not be reused."""

    __tablename__ = "revoked_refresh_tokens"

    jti: Mapped[str] = mapped_column(String(32), primary_key=True)
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
