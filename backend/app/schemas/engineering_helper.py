from pydantic import BaseModel, Field
from typing import List, Optional


class VehicleStateInput(BaseModel):
    vehicle_id: str = Field(..., min_length=1, max_length=50)
    engine_light_on: bool = False
    fault_codes: List[str] = Field(default_factory=list, max_length=20)
    rego_expiry: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    rego_valid: bool = True
    current_mileage: Optional[int] = Field(default=None, ge=0, le=2_000_000)
    last_service_mileage: Optional[int] = Field(default=None, ge=0, le=2_000_000)
    service_interval_km: int = Field(10000, gt=0, le=100_000)
    ownership_status: str = Field("registered", pattern=r"^(registered|unregistered|pending|transfer)$")
    fuel_level_pct: Optional[float] = Field(default=None, ge=0, le=100)
    is_ev: bool = False
    is_phev: bool = False
    battery_soh_pct: Optional[float] = Field(default=None, ge=0, le=100)
    range_km: Optional[int] = Field(default=None, ge=0, le=2000)


class GuidanceOut(BaseModel):
    state: str
    severity: str = Field(..., pattern=r"^(info|warning|critical)$")
    title: str
    message: str
    actions: List[str] = Field(default_factory=list, max_length=10)


class EngineeringHelperResponse(BaseModel):
    vehicle_id: str
    guidances: List[GuidanceOut]
    primary: GuidanceOut
    ai_explanation: Optional[str] = None
    used_fallback: bool = True