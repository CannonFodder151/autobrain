"""Electric charging station price watch models (AUT-412).

``ChargingStationPriceSnapshot`` is the cached price snapshot for EV charging
stations: one row per (station_id, connector_type), upserted on each poll.

``ChargingStationPriceWatchlist`` (AUT-466) is the user's "Electric Spy" watchlist:
the stations + connector types they watch, the move direction they care about,
and the % threshold that triggers an alert. Alerts reuse the user's existing
notification channels (email / push / Discord) — see app.services.notify.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ChargingStationPriceSnapshot(Base):
    __tablename__ = "charging_station_price_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "station_id", "connector_type", name="uq_charging_price_snapshot_station_connector"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    station_id: Mapped[str] = mapped_column(String(64), index=True)
    station_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(80), nullable=True)
    address: Mapped[str | None] = mapped_column(String(240), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    connector_type: Mapped[str] = mapped_column(String(32), index=True)
    price_per_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="AUD")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    previous_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    previous_price_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ChargingStationPriceWatchlist(Base):
    """A user's Electric Spy favourite (station + connector type) to watch for moves.

    One row per (user, station_id, connector_type). ``direction`` is
    "up" / "down" / "both"; ``threshold_pct`` is the minimum absolute % move
    (vs previous price) that fires an alert. ``station_name`` / ``brand`` are
    cached at add time for cheap list rendering.
    """

    __tablename__ = "charging_station_price_watchlist"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "station_id", "connector_type",
            name="uq_charging_watch_user_station_connector",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    station_id: Mapped[str] = mapped_column(String(64), index=True)
    station_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(80), nullable=True)
    connector_type: Mapped[str] = mapped_column(String(32), index=True)
    direction: Mapped[str] = mapped_column(String(8), default="both")  # up|down|both
    threshold_pct: Mapped[float] = mapped_column(Float, default=5.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)