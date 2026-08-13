"""Logbook (ATO trip) schemas."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.services.trip_gps import clean_samples


class GpsSample(BaseModel):
    """One GPS fix on a trip route. `t` is epoch seconds, lat/lon in degrees
    (WGS84). Raw NEO-8M board samples arrive as x10^7 integers with `0,0`
    meaning "no fix" — the parser ([app.services.trip_gps]) normalises those."""

    t: int
    lat: float
    lon: float


class LogEntryCreate(BaseModel):
    started_at: datetime
    start_odometer_km: int | None = None
    start_location: str | None = None
    start_lat: float | None = None
    start_lng: float | None = None
    purpose: str = Field(default="private", pattern="^(work|private)$")
    reason: str | None = None
    gps_samples: list[GpsSample] | None = None

    @field_validator("gps_samples")
    @classmethod
    def _clean(cls, v: list[GpsSample] | None) -> list[GpsSample] | None:
        return clean_samples(v)
    source: str = Field(default="manual", pattern="^(manual|obd_auto|car_auto)$")


class LogEntryUpdate(BaseModel):
    started_at: datetime | None = None
    ended_at: datetime | None = None
    start_odometer_km: int | None = None
    end_odometer_km: int | None = None
    distance_km: float | None = None
    start_location: str | None = None
    end_location: str | None = None
    start_lat: float | None = None
    start_lng: float | None = None
    end_lat: float | None = None
    end_lng: float | None = None
    purpose: str | None = Field(default=None, pattern="^(work|private)$")
    reason: str | None = None
    source: str | None = Field(default=None, pattern="^(manual|obd_auto|car_auto)$")
    status: str | None = Field(default=None, pattern="^(in_progress|completed)$")
    gps_samples: list[GpsSample] | None = None

    @field_validator("gps_samples")
    @classmethod
    def _clean(cls, v: list[GpsSample] | None) -> list[GpsSample] | None:
        return clean_samples(v)


class LogEntryOut(BaseModel):
    id: str
    vehicle_id: str
    started_at: datetime
    ended_at: datetime | None
    start_odometer_km: int | None
    end_odometer_km: int | None
    distance_km: float | None
    purpose: str
    reason: str | None
    source: str
    start_location: str | None
    end_location: str | None
    start_lat: float | None
    start_lng: float | None
    end_lat: float | None
    end_lng: float | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class LogEntryDetail(LogEntryOut):
    """Full trip incl. the GPS route (only returned on the detail endpoint so
    the list stays light — a year of trips with samples would be heavy)."""

    gps_samples: list[GpsSample] = Field(default_factory=list)


class OdometerPhotoResult(BaseModel):
    odometer_km: int | None = None
    confidence: float = 0.0
    model: str = ""


class LogbookStats(BaseModel):
    total_trips: int
    total_distance_km: float
    work_trips: int
    work_distance_km: float
    work_percentage: float
