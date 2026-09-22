"""Schemas for the engineer marketplace (AUT-3661)."""

from __future__ import annotations

from datetime import time
from typing import Any

from pydantic import BaseModel, Field

from app.models.vehicle import Vehicle


class EngineerSearchFilters(BaseModel):
    """Query-parameter filters applied to the engineer marketplace search."""

    q: str | None = Field(
        default=None, max_length=200,
        description="Keyword search across name, specialties, certifications.",
    )
    # Geospatial
    postcode: str | None = Field(default=None, description="Reference postcode to search near.")
    radius_km: float | None = Field(
        default=None, ge=1, le=500,
        description="Search radius in km around the postcode location.",
    )
    lat: float | None = Field(default=None, ge=-90, le=90, description="Direct lat for geospatial filter.")
    lon: float | None = Field(default=None, ge=-180, le=180, description="Direct lon for geospatial query.")

    # Specialty (multi-select)
    specialties: list[str] | None = Field(
        default=None,
        description="Engineer must have ALL of these specialties (exact match on stored values).",
    )

    # Minimum rating
    min_rating: float | None = Field(default=None, ge=0, le=5, description="Minimum overall rating.")

    # Price range
    price_min: float | None = Field(default=None, ge=0, description="Minimum hourly / job price.")
    price_max: float | None = Field(
        default=None, ge=0,
        description="Maximum hourly / job price.",
    )

    # Availability window: ISO day (1=Mon..7=Sun) + time window
    available_day: int | None = Field(default=None, ge=1, le=7, description="ISO weekday for availability search.")
    available_from: time | None = Field(default=None, description="Earliest start time (HH:MM:SS).")
    available_to: time | None = Field(default=None, description="Latest end time (HH:MM:SS).")


class EngineerSortBy(str):
    """Sort key enumeration."""
    RATING = "rating"
    DISTANCE = "distance"
    PRICE = "price"


class EngineerSearchResult(BaseModel):
    id: str
    display_name: str
    specialties: list[str]
    certifications: list[str]
    rating: float
    review_count: int
    price_per_hour: float | None = None
    price_per_job_min: float | None = None
    price_per_job_max: float | None = None
    years_experience: int | None = None
    is_verified: bool = False
    is_active: bool = True
    # Location / distance
    lat: float | None = None
    lon: float | None = None
    distance_km: float | None = None


class EngineerResponse(BaseModel):
    """Single-engineer detail view."""

    id: str
    display_name: str
    email: str
    phone: str | None = None
    lat: float | None = None
    lon: float | None = None
    postcode: str | None = None
    address: str | None = None
    specialties: list[str]
    certifications: list[str]
    years_experience: int | None = None
    rating: float
    review_count: int
    price_per_hour: float | None = None
    price_per_job_min: float | None = None
    price_per_job_max: float | None = None
    availability: list[dict] = Field(default_factory=list)
    is_verified: bool = False
    verification_status: str = "pending"
    created_at: str | None = None
    reviews: list[EngineerReviewSchema] = Field(default_factory=list)


class EngineerReviewSchema(BaseModel):
    id: str
    rating: int
    title: str | None = None
    body: str | None = None
    service_type: str | None = None
    cost: float | None = None
    created_at: str | None = None
    user_display_name: str | None = None


class EngineerSearchResponse(BaseModel):
    """Paginated search response."""

    results: list[EngineerSearchResult]
    total: int
    page: int
    limit: int
    pages: int
    sort: str
    order: str
    filters_applied: dict[str, Any] = Field(default_factory=dict)


class EngineerCreate(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=120)
    email: str = Field(..., max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    postcode: str | None = Field(default=None, max_length=16)
    address: str | None = Field(default=None, max_length=512)
    specialties: list[str] = Field(default_factory=list, max_length=20)
    certifications: list[str] = Field(default_factory=list, max_length=20)
    years_experience: int | None = Field(default=None, ge=0, le=100)
    price_per_hour: float | None = Field(default=None, ge=0)
    price_per_job_min: float | None = Field(default=None, ge=0)
    price_per_job_max: float | None = Field(default=None, ge=0)
    availability: list[dict] = Field(default_factory=list)


class EngineerDetailResponse(BaseModel):
    """Detail view including full profile."""

    engineer: EngineerResponse