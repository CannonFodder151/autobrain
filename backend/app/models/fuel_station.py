"""Servo Spy fuel-price pipeline models (AUT-1817 + AUT-2386).

Normalised station registry + price observations from WA FuelWatch, NSW
FuelCheck and QLD Fuel Prices. Radius queries are done in Python (great-circle
distance), so no PostGIS column is needed (see ``app.services.fuel_feeds``).

AUT-2386 multi-source arbitration: each ``FuelPrice`` row carries the
``source_id`` that produced it plus a computed ``arbitration_score`` (nullable
on legacy rows from before the column existed; backfill in the migration).
``FuelPriceArbitration`` persists the daily winning source per
(station, fuel_type, day) so the /history endpoint and live list stay
consistent across sources.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

def _uuid() -> str:
    return str(uuid.uuid4())

class FuelStation(Base):
    __tablename__ = "fuel_stations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    prices: Mapped[list["FuelPrice"]] = relationship(
        back_populates="station", lazy="selectin", cascade="all, delete-orphan"
    )


class FuelPrice(Base):
    __tablename__ = "fuel_prices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    station_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("fuel_stations.id"), nullable=False, index=True
    )
    fuel_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # AUT-2386: which feed produced this row + its arbitration score
    # (see app.services.fuel_source_arbitration). Nullable so the existing
    # 30-day history rows ingested before this column existed keep working.
    source_id: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    arbitration_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    station: Mapped["FuelStation"] = relationship(back_populates="prices")


class FuelPriceArbitration(Base):
    """AUT-2386: per-day winning source for a (station, fuel_type) bucket.

    Written after every ingest pass by ``fuel_feeds.arbitrate_station_day``.
    Read by the /history endpoint to show the chosen source + score alongside
    each history point, and by the /stations live list to pick the latest
    price per (station, fuel_type) so the live list and history stay
    consistent across feeds that overlap (Ampol/BP/Costco show up in NSW
    FuelCheck + SAFPIS + QLD Fuel Prices).
    """

    __tablename__ = "fuel_price_arbitrations"
    __table_args__ = (
        UniqueConstraint(
            "station_id", "fuel_type", "day",
            name="uq_fuel_arbitration_station_fuel_day",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    station_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("fuel_stations.id"), nullable=False, index=True
    )
    fuel_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # Calendar day in UTC (00:00 of that day) — the bucket arbitration keys on.
    day: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Winning source + price + score, copied into this row for cheap reads.
    source_id: Mapped[str] = mapped_column(String(16), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    arbitration_score: Mapped[float] = mapped_column(Float, nullable=False)
    # How many candidate sources fed the decision (>=1; >1 means arbitration
    # had something to do).
    candidate_count: Mapped[int] = mapped_column(default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
