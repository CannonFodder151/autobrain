"""Servo Spy fuel-price pipeline models (AUT-1817) + multi-source arbitration
(AUT-2381).

Normalised station registry + price observations from WA FuelWatch, NSW
FuelCheck and QLD Fuel Prices (and future SA/TAS/NT per AUT-2374). Radius
queries are done in Python (great-circle distance), so no PostGIS column is
needed (see ``app.services.fuel_feeds``).

``FuelPrice`` also carries the arbitration result of AUT-2381: ``source`` is
the upstream that emitted the row, ``best_source`` is the source that won
the per-(station,fuel_type,day) arbitration, and ``source_score`` is the
score the winner received. ``flag_reason`` records any consistency flag
(>30 cpl disagreement with the regional median) so admin can override.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, func
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
    # AUT-2381: which upstream emitted this row ("wa"/"nsw"/"qld"/...).
    source: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    # AUT-2381: arbitration winner for (station_id, fuel_type, day). Same value
    # across all rows for the same key on a given day; only one row's
    # ``best_source`` matches ``source`` (the winning row).
    best_source: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    source_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # AUT-2381: consistency flag, e.g. "outlier>30cpl"; null when clean.
    flag_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)

    station: Mapped["FuelStation"] = relationship(back_populates="prices")
