"""Maintenance service records.

Status model:
  - "scheduled": a future/planned service (from AI diagnostics or predictions).
    Not counted in spend/analytics and excluded from reports until completed.
  - "completed": a finished service that counts towards totals.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ServiceRecord(Base):
    __tablename__ = "service_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    vehicle_id: Mapped[str] = mapped_column(String(36), ForeignKey("vehicles.id"), index=True)
    service_date: Mapped[date] = mapped_column(Date, index=True)
    odometer_km: Mapped[int] = mapped_column(Integer, nullable=False)
    service_type: Mapped[str] = mapped_column(String(60))  # scheduled/repair/tire/oil/custom
    description: Mapped[str | None] = mapped_column(Text)
    workshop: Mapped[str | None] = mapped_column(String(255))
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(8), default="AUD")
    notes: Mapped[str | None] = mapped_column(Text)
    ai_prediction: Mapped[str | None] = mapped_column(Text)
    next_due_km: Mapped[int | None] = mapped_column(Integer)
    next_due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="completed", nullable=False, index=True)
    completed_date: Mapped[date | None] = mapped_column(Date)
    steps: Mapped[str | None] = mapped_column(Text)  # JSON list of work steps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    items: Mapped[list["ServiceItem"]] = relationship(
        back_populates="service", cascade="all, delete-orphan", lazy="selectin"
    )


class ServiceItem(Base):
    __tablename__ = "service_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    service_id: Mapped[str] = mapped_column(String(36), ForeignKey("service_records.id"), index=True)
    part_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("parts.id"))
    name: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_cost: Mapped[float] = mapped_column(Float, default=0.0)
    kind: Mapped[str] = mapped_column(String(20), default="item", nullable=False)  # part/labour/item
    part_no: Mapped[str | None] = mapped_column(String(120))
    labour_hours: Mapped[float | None] = mapped_column(Float)
    labour_rate: Mapped[float | None] = mapped_column(Float)

    service: Mapped["ServiceRecord"] = relationship(back_populates="items")
