"""Maintenance service records."""

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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ServiceItem(Base):
    __tablename__ = "service_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    service_id: Mapped[str] = mapped_column(String(36), ForeignKey("service_records.id"), index=True)
    part_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("parts.id"))
    name: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_cost: Mapped[float] = mapped_column(Float, default=0.0)
    labour_hours: Mapped[float | None] = mapped_column(Float)
    labour_rate: Mapped[float | None] = mapped_column(Float)
