"""Servo Spy fuel-price pipeline models (AUT-1817).

Normalised station registry + price observations from WA FuelWatch, NSW
FuelCheck and QLD Fuel Prices. Radius queries are done in Python (great-circle
distance), so no PostGIS column is needed (see ``app.services.fuel_feeds``).

The servo-spy price row lives in its own ``fuel_station_prices`` table to avoid
colliding with the AUT-1813 NSW snapshot row in ``fuel_prices`` (different
schema: FK to ``fuel_stations`` here, state+station_code unique there). AUT-2277.
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

    prices: Mapped[list["FuelStationPrice"]] = relationship(
        back_populates="station", lazy="selectin", cascade="all, delete-orphan"
    )


class FuelStationPrice(Base):
    __tablename__ = "fuel_station_prices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    station_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("fuel_stations.id"), nullable=False, index=True
    )
    fuel_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    station: Mapped["FuelStation"] = relationship(back_populates="prices")
