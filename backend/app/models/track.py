"""Track session model for track-aware maintenance schedule."""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class TrackSeverity(str):
    """Track session severity levels with road-mile multipliers.

    1 track mile ≈ N road miles depending on severity:
    - light: 3x (gentle lapping, driver education)
    - medium: 4x (club racing, time attack)
    - severe: 5x (endurance, sprint racing, heavy braking zones)
    """

    LIGHT = "light"
    MEDIUM = "medium"
    SEVERE = "severe"

    _MULTIPLIERS = {
        LIGHT: 3,
        MEDIUM: 4,
        SEVERE: 5,
    }

    @classmethod
    def multiplier(cls, severity: str) -> int:
        return cls._MULTIPLIERS.get(severity, 3)

    @classmethod
    def effective_miles(cls, track_miles: int, severity: str) -> int:
        """Convert track miles to equivalent road miles."""
        return track_miles * cls._MULTIPLIERS.get(severity, 3)


class TrackSession(Base):
    """Track day / session logged against a vehicle.

    Used to calculate effective mileage for maintenance scheduling.
    Each track mile is multiplied by severity factor (3-5x) to get
    equivalent road miles that accelerate service intervals.
    """

    __tablename__ = "track_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    vehicle_id: Mapped[str] = mapped_column(String(36), ForeignKey("vehicles.id"), index=True)
    session_date: Mapped[date] = mapped_column(Date, index=True)
    track_name: Mapped[str] = mapped_column(String(120))
    track_miles: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default=TrackSeverity.LIGHT, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500))
    effective_road_miles: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )