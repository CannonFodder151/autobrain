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


class EngineeringHelperSummary(BaseModel):
    primary_state: str
    primary_severity: str
    primary_title: str
    primary_message: str
    ai_explanation: Optional[str] = None
    used_fallback: bool = True


class HealthScoreResponse(BaseModel):
    vehicle_id: str
    overall_score: float = Field(ge=0, le=100)
    overall_status: HealthStatus
    components: list[HealthScoreComponent]
    last_updated: str
    mileage: Optional[int] = None
    engineering_helper: Optional[EngineeringHelperSummary] = None


class VehicleNotFoundError(BaseModel):
    detail: str = "Vehicle not found"