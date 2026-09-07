"""Electric Spy charging-station models (AUT-2435).

Normalised station + connector registry sourced from Open Charge Map (MVP),
with optional local-price overrides when network pricing data is available.
Radius queries use the same great-circle haversine pattern as fuel_stations.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ChargingStation(Base):
    __tablename__ = "charging_stations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    ocm_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    network: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    connectors: Mapped[list["ChargingConnector"]] = relationship(
        back_populates="station", lazy="selectin", cascade="all, delete-orphan"
    )


class ChargingConnector(Base):
    __tablename__ = "charging_connectors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    station_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("charging_stations.id"), nullable=False, index=True
    )
    connector_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    max_power_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_per_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)

    station: Mapped["ChargingStation"] = relationship(back_populates="connectors")
