"""Petrol price feed rows (AUT-1813): cached NSW Fuel API snapshots.

One row per (state, station_code, fuel_type) — upserted on each successful
daily poll. The map read API serves the latest cached set; the offline path
serves these rows (never hard-fails a user request). The poll-state row is
keyed by instance_id so each AutoBrain instance polls its provider at most
once per FUEL_NSW_POLL_HOURS (currently 24h).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class NSWFuelPrice(Base):
    __tablename__ = "nsw_fuel_prices"
    __table_args__ = (UniqueConstraint("state", "station_code", "fuel_type", name="uq_nsw_fuel_price_station_fuel"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    state: Mapped[str] = mapped_column(String(8), index=True)
    station_code: Mapped[str] = mapped_column(String(32), index=True)
    station_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(80), nullable=True)
    address: Mapped[str | None] = mapped_column(String(240), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    fuel_type: Mapped[str] = mapped_column(String(16), index=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="AUD")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class NSWFuelPricePollState(Base):
    """Per-instance, per-state last-poll timestamp to enforce once/day/instance."""

    __tablename__ = "nsw_fuel_price_poll_state"
    __table_args__ = (UniqueConstraint("instance_id", "state", name="uq_nsw_fuel_poll_instance_state"),)

    instance_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    state: Mapped[str] = mapped_column(String(8), primary_key=True)
    last_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)