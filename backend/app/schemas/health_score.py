"""Vehicle Health Score schemas."""

from pydantic import BaseModel, Field


class PredictiveAlert(BaseModel):
    component: str
    alert_type: str  # service_overdue, part_reorder, obd_active, diagnostic_open, efficiency_drop
    severity: str  # low/medium/high/critical
    message: str
    estimated_cost: float | None = None
    due_in_km: int | None = None
    due_in_days: int | None = None
    source_id: str | None = None  # link to the source record


class ScoreBreakdown(BaseModel):
    diagnostics: float = Field(description="0-25 points from diagnostic history")
    maintenance: float = Field(description="0-25 points from service records")
    fuel_efficiency: float = Field(description="0-25 points from fuel efficiency data")
    obd_codes: float = Field(description="0-15 points from OBD-II fault codes")
    parts: float = Field(description="0-10 points from parts inventory health")


class HealthScoreResponse(BaseModel):
    score: int = Field(ge=0, le=100, description="Vehicle Health Score 0-100")
    label: str  # excellent/good/fair/poor/critical
    breakdown: ScoreBreakdown
    confidence: float = Field(ge=0, le=1)
    alerts: list[PredictiveAlert] = []
    signals: list[str] = []
    model: str  # rule-based or rule-based+ai
