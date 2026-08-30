"""Parts inventory and stock movements."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Part(Base):
    __tablename__ = "parts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    vehicle_id: Mapped[str] = mapped_column(String(36), ForeignKey("vehicles.id"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(120), index=True)
    category: Mapped[str] = mapped_column(String(60), default="other")
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    min_quantity: Mapped[int] = mapped_column(Integer, default=0)
    unit_cost: Mapped[float] = mapped_column(Float, default=0.0)
    supplier: Mapped[str | None] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    warranty_months: Mapped[int | None] = mapped_column(Integer)
    ai_reorder_suggestion: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PartMovement(Base):
    __tablename__ = "part_movements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    part_id: Mapped[str] = mapped_column(String(36), ForeignKey("parts.id"), index=True)
    delta: Mapped[int] = mapped_column(Integer)  # positive = in, negative = out
    reason: Mapped[str] = mapped_column(String(60))  # purchase/service/scan/adjust
    service_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("service_records.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
