"""Vehicle Health Score model — one row per vehicle, cached score 0–100."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class VehicleHealthScore(Base):
    __tablename__ = "vehicle_health_scores"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    vehicle_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("vehicles.id"), index=True, unique=True
    )
    score: Mapped[int] = mapped_column(Integer, default=0)  # 0–100
    last_computed: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    computed_by: Mapped[str | None] = mapped_column(
        String(64), default="deterministic"
    )  # deterministic / ai
    notes: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )