"""OBD-II code schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class ObdCodeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=16)
    description: str | None = None
    source: str = Field(default="obd", pattern="^(obd|manual)$")


class ObdCodeUpdate(BaseModel):
    description: str | None = None
    is_resolved: bool | None = None


class ObdCodeOut(BaseModel):
    id: str
    vehicle_id: str
    code: str
    description: str | None
    source: str
    is_resolved: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ObdVinRequest(BaseModel):
    vin: str = Field(min_length=5, max_length=17)


class ObdSettingsOut(BaseModel):
    enabled: bool
    auto_connect: bool
