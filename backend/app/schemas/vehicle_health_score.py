"""Vehicle Health Score schemas."""

from datetime import datetime

from pydantic import BaseModel, Field, field_serializer


class VehicleHealthScoreSummary(BaseModel):
    """Summary used in overview/list views."""

    vehicle_id: str = Field(alias="id")
    nickname: str | None = None
    score: int = Field(default=0, ge=0, le=100)
    status_label: str = Field(default="unknown")  # healthy/at-risk/needs-attention
    last_computed: str | None = None


class VehicleHealthScoreCreate(BaseModel):
    """Input payload for computing a health score."""

    force: bool = Field(default=False, description="Force recompute even if recent score exists")


class VehicleHealthScoreOut(BaseModel):
    """Full health score response."""

    vehicle_id: str
    nickname: str | None = None
    score: int = Field(ge=0, le=100, description="Health score 0–100")
    status_label: str = Field(default="unknown")  # healthy/at-risk/needs-attention
    breakdown: dict = Field(default_factory=dict, description="Per-category contributions")
    last_computed: str | None = None
    computed_by: str = Field(default="deterministic")  # deterministic / ai

    model_config = {"from_attributes": True}

    @field_serializer("last_computed")
    def _serialise_last_computed(self, v):
        if isinstance(v, datetime):
            return v.isoformat()
        return v