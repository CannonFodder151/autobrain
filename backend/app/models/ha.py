"""ha_integrations (AUT-2541).

Per-user opaque token so an external Home Assistant instance can poll
AutoBrain for analytics + service-interval data. Token shape mirrors
`devices`: random `abha_<hex>` prefix, sha256 digest only in DB, prefix
index for lookup, constant-time compare.

Optional `vehicle_id` scopes a token to one vehicle; NULL = every
accessible vehicle for the owning user.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class HaIntegration(Base):
    __tablename__ = "ha_integrations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    label: Mapped[str] = mapped_column(String(80), default="Home Assistant")
    api_key_prefix: Mapped[str] = mapped_column(String(10), index=True)
    api_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    vehicle_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("vehicles.id"))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
