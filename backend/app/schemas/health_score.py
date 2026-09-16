"""Vehicle Health Score schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class HealthScoreBreakdown(BaseModel):
    condition: dict = Field(
        description="Condition component score and detail",
    )
    obd_codes: dict = Field(
        description="Active OBD codes penalty and detail",
    )
    diagnostic_severity: dict = Field(
        description="Diagnostic severity penalty and detail",
    )
    fuel_efficiency: dict = Field(
        description="Fuel efficiency score and detail",
    )
    service_overdue: dict = Field(
        description="Service overdue penalty and detail",
    )
    parts_wear: dict = Field(
        description="Parts wear penalty and detail",
    )


class HealthScore(BaseModel):
    score: int = Field(description="Vehicle Health Score (0-100), higher is better")
    grade: str = Field(description="Letter grade: A, B, C, D, F")
    breakdown: HealthScoreBreakdown = Field(description="Per-component score breakdown")
    alerts: list[str] = Field(
        description="List of active alerts / issues flagged by the score",
        default=[],
    )
    last_updated: datetime = Field(description="When the score was computed")

    model_config = {"from_attributes": True}


class HealthScoreRequest(BaseModel):
    """Request to recompute the health score for a vehicle.

    Optional fields allow overriding vehicle-sourced values
    (e.g. passing the latest odometer reading from the mobile app).
    """

    odometer_km: int | None = Field(
        default=None,
        description="Latest odometer reading in km (optional override)",
    )
    condition: str | None = Field(
        default=None,
        description="Override vehicle condition (excellent/good/fair/poor)",
    )