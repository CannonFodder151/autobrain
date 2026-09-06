"""Petrol price feed rows (AUT-1813) + servo-spy favourites (AUT-1859).

``FuelPriceSnapshot`` is the cached NSW Fuel API snapshot: one row per
(state, station_code, fuel_type), upserted on each successful daily poll. The
map read API serves the latest cached set; the offline path serves these rows
(never hard-fails a user request). ``previous_price`` / ``previous_price_at``
hold the last *distinct* price so day-over-day % moves can be computed
deterministically with no AI. The poll-state row is keyed by instance_id so
each AutoBrain instance polls its provider at most once per FUEL_NSW_POLL_HOURS.

``FuelPriceWatchlist`` (AUT-1859) is the user's "servo spy" favourites set: the
stations + fuel types they watch, the move direction they care about, and the
% threshold that triggers an alert. Alerts reuse the user's existing
notification channels (email / push / Discord) — see app.services.notify.

Class is named ``FuelPriceSnapshot`` and stored in ``fuel_price_snapshots`` to
avoid colliding with the AUT-1817 Servo Spy ``FuelPrice`` model in
``fuel_station`` (which lives in the ``fuel_prices`` table with an FK to
``fuel_stations``).
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


class FuelPriceSnapshot(Base):
    __tablename__ = "fuel_price_snapshots"
    __table_args__ = (UniqueConstraint("state", "station_code", "fuel_type", name="uq_fuel_price_snapshot_station_fuel"),)


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
    # AUT-1859: last *distinct* price, used to compute day-over-day % change.
    previous_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    previous_price_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FuelPriceWatchlist(Base):
    """A user's servo-spy favourite (station + fuel type) to watch for moves.

    One row per (user, state, station_code, fuel_type). ``direction`` is
    "up" / "down" / "both"; ``threshold_pct`` is the minimum absolute % move
    (vs previous price) that fires an alert. ``station_name`` / ``brand`` are
    cached at add time for cheap list rendering.
    """

    __tablename__ = "fuel_price_watchlist"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "state", "station_code", "fuel_type",
            name="uq_fuel_watch_user_station_fuel",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    state: Mapped[str] = mapped_column(String(8), index=True)
    station_code: Mapped[str] = mapped_column(String(32), index=True)
    station_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(80), nullable=True)
    fuel_type: Mapped[str] = mapped_column(String(16), index=True)
    direction: Mapped[str] = mapped_column(String(8), default="both")  # up|down|both
    threshold_pct: Mapped[float] = mapped_column(Float, default=5.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FuelPricePollState(Base):
    """Per-instance, per-state last-poll timestamp to enforce once/day/instance."""

    __tablename__ = "fuel_price_poll_state"
    __table_args__ = (UniqueConstraint("instance_id", "state", name="uq_fuel_poll_instance_state"),)

    instance_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    state: Mapped[str] = mapped_column(String(8), primary_key=True)
    last_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)