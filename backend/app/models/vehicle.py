"""Vehicle profile and unified timeline event model."""

import enum
import uuid
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class PowertrainType(str, enum.Enum):
    """Canonical powertrain tokens exposed in API responses (AUT-2434).

    Stored as the enum's string ``value`` (e.g. ``"ICE"``) so DB rows stay
    readable without a join. New vehicles default to ICE; pre-existing rows
    are backfilled to ICE by the AUT-2434 alembic migration.
    """

    ICE = "ICE"
    EV = "EV"
    HEV = "HEV"
    PHEV = "PHEV"


if TYPE_CHECKING:
    from app.models.service import ServiceRecord
    from app.models.fuel import FuelLog
    from app.models.mod import Modification
    from app.models.diagnostic import Diagnostic


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    nickname: Mapped[str] = mapped_column(String(120), nullable=False)
    rego: Mapped[str | None] = mapped_column(String(20), index=True)
    rego_state: Mapped[str | None] = mapped_column(String(8), index=True)
    vin: Mapped[str | None] = mapped_column(String(17))
    make: Mapped[str | None] = mapped_column(String(80))
    model: Mapped[str | None] = mapped_column(String(80))
    colour: Mapped[str | None] = mapped_column(String(30))
    body_type: Mapped[str | None] = mapped_column(String(40))
    year: Mapped[int | None] = mapped_column(Integer)
    engine: Mapped[str | None] = mapped_column(String(120))
    transmission: Mapped[str | None] = mapped_column(String(60))
    odometer_km: Mapped[int | None] = mapped_column(Integer, default=0)
    condition: Mapped[str] = mapped_column(String(20), default="good")  # excellent/good/fair/poor
    vehicle_type: Mapped[str] = mapped_column(String(20), default="car")  # car/motorcycle
    is_primary: Mapped[bool] = mapped_column(default=False)
    club_reg: Mapped[bool] = mapped_column(default=False)  # club reg => no ATO logbook
    auto_suggest_service: Mapped[bool] = mapped_column(default=False)  # AUT-1275: suggest next service when odo updates
    fuel_type: Mapped[str | None] = mapped_column(String(16))  # AUT-1819: drives default price shown on map/list
    powertrain: Mapped[str] = mapped_column(String(8), default=PowertrainType.ICE.value)  # AUT-2434: ICE/EV/HEV/PHEV
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class VehicleEvent(Base):
    """Unified timeline entry across services, fuel, mods and diagnostics."""

    __tablename__ = "vehicle_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    vehicle_id: Mapped[str] = mapped_column(String(36), ForeignKey("vehicles.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(20), index=True)  # service/fuel/mod/diagnostic
    title: Mapped[str] = mapped_column(String(255))
    occurred_on: Mapped[date] = mapped_column(index=True)
    odometer_km: Mapped[int | None] = mapped_column(Integer)
    amount: Mapped[float | None] = mapped_column()
    source_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
