from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class HealthStatus(str, Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    CRITICAL = "critical"


class HealthScoreComponent(BaseModel):
    name: str
    score: float = Field(ge=0, le=100)
    status: HealthStatus
    details: Optional[str] = None


class HealthScoreResponse(BaseModel):
    vehicle_id: str
    overall_score: float = Field(ge=0, le=100)
    overall_status: HealthStatus
    components: list[HealthScoreComponent]
    last_updated: str
    mileage: Optional[int] = None


class VehicleNotFoundError(BaseModel):
    detail: str = "Vehicle not found"