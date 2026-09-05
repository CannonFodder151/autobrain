"""Electricity charge logs (EV charging sessions).

Mirrors the fuel-log shape: a vehicle records every charge (kWh in, cost,
$/kWh) and the chain of full charges yields km/kWh efficiency. Same
deterministic-only path as fuel (no AI; receipts are uploaded but the
parsed fields default to NULL).
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ElectricityLog(Base):
    __tablename__ = "electricity_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    vehicle_id: Mapped[str] = mapped_column(String(36), ForeignKey("vehicles.id"), index=True)
    charge_date: Mapped[date] = mapped_column(Date, index=True)
    odometer_km: Mapped[int] = mapped_column(Integer)
    kwh: Mapped[float] = mapped_column(Float)
    price_per_kwh: Mapped[float] = mapped_column(Float)
    total_cost: Mapped[float] = mapped_column(Float)
    is_full_charge: Mapped[bool] = mapped_column(default=True)
    notes: Mapped[str | None] = mapped_column(String(500))
    distance_km: Mapped[float | None] = mapped_column(Float)  # since previous full charge
    km_per_kwh: Mapped[float | None] = mapped_column(Float)
    cost_per_km: Mapped[float | None] = mapped_column(Float)
    receipt_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("receipts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    receipt: Mapped["Receipt | None"] = relationship(foreign_keys=[receipt_id], lazy="selectin")
