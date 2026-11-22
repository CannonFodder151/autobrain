"""Electric Spy charging-station price pipeline models (AUT-412).

Normalised station registry + price observations from WA/QLD government feeds.
Radius queries are done in Python (great-circle distance), so no PostGIS column
is needed. Multi-source arbitration mirrors Servo Spy (AUT-2386).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

def _uuid() -> str:
    return str(uuid.uuid4())

class ChargingStation(Base):
    __tablename__ = "charging_stations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    connector_types: Mapped[str | None] = mapped_column(String(128), nullable=True)  # CSV: CCS2,CHAdeMO,Type2
    max_power_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    prices: Mapped[list["ChargingPrice"]] = relationship(
        back_populates="station", lazy="selectin", cascade="all, delete-orphan"
    )

class ChargingPrice(Base):
    __tablename__ = "charging_prices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    station_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("charging_stations.id"), nullable=False, index=True
    )
    connector_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    price_per_kwh: Mapped[float] = mapped_column(Float, nullable=False)  # cents per kWh
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    arbitration_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    station: Mapped["ChargingStation"] = relationship(back_populates="prices")

class ChargingPriceArbitration(Base):
    """Per-day winning source for a (station, connector_type) bucket.

    Written after every ingest pass by the arbitration task.
    Read by the /history endpoint and the /stations live list.
    """

    __tablename__ = "charging_price_arbitrations"
    __table_args__ = (
        UniqueConstraint(
            "station_id", "connector_type", "day",
            name="uq_charging_arbitration_station_connector_day",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    station_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("charging_stations.id"), nullable=False, index=True
    )
    connector_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    day: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_id: Mapped[str] = mapped_column(String(16), nullable=False)
    price_per_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    arbitration_score: Mapped[float] = mapped_column(Float, nullable=False)
    candidate_count: Mapped[int] = mapped_column(default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ChargingPriceWatchlist(Base):
    """A user's Electric Spy favourite (station + connector) to watch for prices."""

    __tablename__ = "charging_price_watchlist"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "station_id", "connector_type",
            name="uq_charging_watch_user_station_connector",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    station_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("charging_stations.id"), nullable=False, index=True
    )
    connector_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    target_price_per_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )