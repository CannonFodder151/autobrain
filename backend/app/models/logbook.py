"""ATO logbook trips (club-reg disabled vehicles).

Every trip is recorded for ATO logbook claiming: a start (time, date, GPS
location, odometer) and an optional end (time, date, odometer, photo). Trips
marked `purpose=work` count towards the business-use percentage.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class LogEntry(Base):
    __tablename__ = "logbook_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    vehicle_id: Mapped[str] = mapped_column(String(36), ForeignKey("vehicles.id"), index=True)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    start_odometer_km: Mapped[int | None] = mapped_column(Integer)
    end_odometer_km: Mapped[int | None] = mapped_column(Integer)
    distance_km: Mapped[float | None] = mapped_column(Float)

    purpose: Mapped[str] = mapped_column(String(12), default="private")  # work/private
    reason: Mapped[str | None] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual/obd_auto

    start_location: Mapped[str | None] = mapped_column(String(255))
    end_location: Mapped[str | None] = mapped_column(String(255))
    start_lat: Mapped[float | None] = mapped_column(Float)
    start_lng: Mapped[float | None] = mapped_column(Float)
    end_lat: Mapped[float | None] = mapped_column(Float)
    end_lng: Mapped[float | None] = mapped_column(Float)

    start_photo_key: Mapped[str | None] = mapped_column(String(500))
    end_photo_key: Mapped[str | None] = mapped_column(String(500))

    # Trip GPS polyline: [{"t": <epoch seconds>, "lat": deg, "lon": deg}, ...]
    # deterministic raw coordinates — no AI. Rendered as the trip route on a map.
    gps_samples: Mapped[list | None] = mapped_column(JSON)

    status: Mapped[str] = mapped_column(String(20), default="in_progress")  # in_progress/completed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
