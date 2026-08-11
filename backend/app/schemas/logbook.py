"""Logbook (ATO trip) schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class LogEntryCreate(BaseModel):
    started_at: datetime
    start_odometer_km: int | None = None
    start_location: str | None = None
    start_lat: float | None = None
    start_lng: float | None = None
    purpose: str = Field(default="private", pattern="^(work|private)$")
    reason: str | None = None
    source: str = Field(default="manual", pattern="^(manual|obd_auto)$")


class LogEntryUpdate(BaseModel):
    started_at: datetime | None = None
    ended_at: datetime | None = None
    start_odometer_km: int | None = None
    end_odometer_km: int | None = None
    start_location: str | None = None
    end_location: str | None = None
    start_lat: float | None = None
    start_lng: float | None = None
    end_lat: float | None = None
    end_lng: float | None = None
    purpose: str | None = Field(default=None, pattern="^(work|private)$")
    reason: str | None = None
    source: str | None = Field(default=None, pattern="^(manual|obd_auto)$")
    status: str | None = Field(default=None, pattern="^(in_progress|completed)$")


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
