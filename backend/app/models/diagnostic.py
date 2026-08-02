"""AI diagnostic records."""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Diagnostic(Base):
    __tablename__ = "diagnostics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    vehicle_id: Mapped[str] = mapped_column(String(36), ForeignKey("vehicles.id"), index=True)
    symptoms: Mapped[str] = mapped_column(Text, nullable=False)
    ai_response: Mapped[dict] = mapped_column(Text)  # JSON payload from AI layer
    summary: Mapped[str | None] = mapped_column(String(500))
    severity: Mapped[str | None] = mapped_column(String(20))  # low/medium/high/critical
    estimated_cost: Mapped[float | None] = mapped_column(Float)
    parts_needed: Mapped[dict | None] = mapped_column(Text)
    added_to_service: Mapped[bool] = mapped_column(default=False)
    linked_service_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("service_records.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
