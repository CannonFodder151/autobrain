"""Tire inventory and usage tracking.

Tracks tire sets per vehicle with heat cycle counting from session logs,
tread depth monitoring with deterministic wear predictions, and end-of-life
alerts based on compound, usage, and heat cycles.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


# Deterministic wear estimates (km) per compound type for full tread life.
# No AI — pure lookup based on compound category.
COMPOUND_LIFE_KM = {
    "street": 40000,
    "all_season": 50000,
    "performance": 25000,
    "track": 8000,
    "racing": 4000,
    "rally": 6000,
    "wet": 10000,
    "drag": 2000,
}

# Default tread depth specs (mm) per compound type when new.
COMPOUND_NEW_TREAD_MM = {
    "street": 8.0,
    "all_season": 8.5,
    "performance": 7.0,
    "track": 5.0,
    "wet": 8.0,
    "racing": 4.0,
    "rally": 6.0,
    "drag": 3.0,
}

# Heat cycle penalty: each heat cycle reduces effective life by this factor.
# Derived from motorsport tire engineering data (deterministic, no AI).
HEAT_CYCLE_PENALTY_PER_CYCLE = 0.03  # 3% reduction per heat cycle

# Minimum safe tread depth (mm) — below this = end of life.
MIN_TREAD_MM = 1.6  # legal minimum AU/US


class TireSet(Base):
    """A set of tires mounted on a vehicle (e.g., 'Front Summer Set')."""

    __tablename__ = "tire_sets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    vehicle_id: Mapped[str] = mapped_column(String(36), ForeignKey("vehicles.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    brand: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    size: Mapped[str] = mapped_column(String(30), nullable=False)  # e.g. "245/40R18"
    compound: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    position: Mapped[str | None] = mapped_column(String(20))  # front/rear/none
    purchase_date: Mapped[date | None] = mapped_column(Date)
    purchase_cost: Mapped[float | None] = mapped_column(Float)
    new_tread_mm: Mapped[float] = mapped_column(Float, default=8.0)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    sessions: Mapped[list["TireSession"]] = relationship(
        back_populates="tire_set", cascade="all, delete-orphan", lazy="selectin"
    )
    tread_readings: Mapped[list["TireTreadReading"]] = relationship(
        back_populates="tire_set", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def heat_cycles(self) -> int:
        """Auto-counted from session count (each session = 1 heat cycle)."""
        return len(self.sessions) if self.sessions else 0

    @property
    def total_sessions(self) -> int:
        return len(self.sessions) if self.sessions else 0

    @property
    def remaining_tread_mm(self) -> float | None:
        """Most recent tread depth reading, or None if never measured."""
        if not self.tread_readings:
            return None
        latest = sorted(self.tread_readings, key=lambda r: r.reading_date)[-1]
        return latest.depth_mm

    @property
    def predicted_remaining_km(self) -> float | None:
        """Deterministic prediction of remaining life in km.

        Based on compound life estimate, current tread depth, heat cycles,
        and total distance covered. No AI — pure arithmetic.
        """
        base_life = COMPOUND_LIFE_KM.get(self.compound, 25000)
        # Apply heat cycle penalty
        cycles = self.heat_cycles
        cycle_factor = max(0.1, 1.0 - (cycles * HEAT_CYCLE_PENALTY_PER_CYCLE))
        effective_life = base_life * cycle_factor
        # Tread depth ratio
        current = self.remaining_tread_mm
        if current is None:
            return effective_life  # no reading — assume full life remaining
        if current <= MIN_TREAD_MM:
            return 0.0
        new_tread = self.new_tread_mm or COMPOUND_NEW_TREAD_MM.get(self.compound, 8.0)
        tread_ratio = current / new_tread
        return round(effective_life * tread_ratio, 0)

    @property
    def end_of_life_pct(self) -> float | None:
        """Percentage of life consumed (0-100). None if no data."""
        predicted = self.predicted_remaining_km
        if predicted is None:
            return None
        base_life = COMPOUND_LIFE_KM.get(self.compound, 25000)
        cycles = self.heat_cycles
        cycle_factor = max(0.1, 1.0 - (cycles * HEAT_CYCLE_PENALTY_PER_CYCLE))
        effective_life = base_life * cycle_factor
        if effective_life <= 0:
            return 100.0
        return round((1.0 - predicted / effective_life) * 100, 1)

    @property
    def is_end_of_life(self) -> bool:
        """True if tread is at or below minimum safe depth."""
        current = self.remaining_tread_mm
        if current is None:
            return False
        return current <= MIN_TREAD_MM


class TireSession(Base):
    """A single session or track day usage log for a tire set."""

    __tablename__ = "tire_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tire_set_id: Mapped[str] = mapped_column(String(36), ForeignKey("tire_sets.id"), index=True)
    session_date: Mapped[date] = mapped_column(Date, index=True)
    track_name: Mapped[str | None] = mapped_column(String(200))
    session_type: Mapped[str] = mapped_column(String(20), default="street")  # street/track/autocross/race
    distance_km: Mapped[float | None] = mapped_column(Float)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    weather: Mapped[str | None] = mapped_column(String(50))  # dry/wet/hot/cold
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tire_set: Mapped["TireSet"] = relationship(back_populates="sessions")


class TireTreadReading(Base):
    """Manual tread depth measurement entry."""

    __tablename__ = "tire_tread_readings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tire_set_id: Mapped[str] = mapped_column(String(36), ForeignKey("tire_sets.id"), index=True)
    reading_date: Mapped[date] = mapped_column(Date, index=True)
    depth_mm: Mapped[float] = mapped_column(Float, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tire_set: Mapped["TireSet"] = relationship(back_populates="tread_readings")
