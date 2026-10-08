"""Track-day and vehicle cost entries."""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class CostCategory(str, enum.Enum):
    TRACK_DAY = "track_day"       # Track day entry fees
    FUEL = "fuel"                 # Fuel purchases
    TIRES = "tires"               # Tire purchases
    PARTS = "parts"               # Parts/consumables
    TRAVEL = "travel"             # Travel/accommodation
    INSURANCE = "insurance"       # Insurance


class CostEntry(Base):
    __tablename__ = "cost_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    vehicle_id: Mapped[str] = mapped_column(String(36), ForeignKey("vehicles.id"), index=True)
    category: Mapped[CostCategory] = mapped_column(Enum(CostCategory, native_enum=False), index=True)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="AUD")
    date: Mapped[date] = mapped_column(Date, index=True)
    odometer_km: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    vendor: Mapped[str | None] = mapped_column(String(255))
    receipt_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("receipts.id"))
    # Track-day specific fields
    track_name: Mapped[str | None] = mapped_column(String(255))
    laps_completed: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())