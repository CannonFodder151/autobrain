"""Vehicle modifications."""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.db.types import JSONList


def _uuid() -> str:
    return str(uuid.uuid4())


class Modification(Base):
    __tablename__ = "modifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    vehicle_id: Mapped[str] = mapped_column(String(36), ForeignKey("vehicles.id"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(60), default="other")
    # performance/audio/visual/interior/exterior/suspension/engine/exhaust/brakes/other
    brand: Mapped[str | None] = mapped_column(String(120))
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    install_date: Mapped[date | None] = mapped_column(Date)
    odometer_km: Mapped[int | None] = mapped_column()
    notes: Mapped[str | None] = mapped_column(Text)
    photo_keys: Mapped[list | None] = mapped_column(JSONList)  # JSON list of MinIO keys
    ai_impact: Mapped[dict | None] = mapped_column(Text)  # JSON from AI mod_impact module
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
