"""Resale valuation snapshots."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ValuationSnapshot(Base):
    __tablename__ = "valuation_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    vehicle_id: Mapped[str] = mapped_column(String(36), ForeignKey("vehicles.id"), index=True)
    estimated_value: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="AUD")
    factors: Mapped[dict | None] = mapped_column(Text)  # JSON breakdown
    recommendations: Mapped[list | None] = mapped_column(Text)  # JSON list
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
