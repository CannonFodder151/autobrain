from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

router = APIRouter()

_FUEL: Dict[str, List[dict]] = {}
_SERVICE: Dict[str, List[dict]] = {}


def _id() -> str:
    return str(uuid.uuid4())


class FuelFillUpIn(BaseModel):
    vehicleId: str
    date: str
    litres: float = Field(gt=0)
    pricePerLitre: float = Field(ge=0)
    odometer: float = Field(ge=0)
    station: Optional[str] = None
    fuelType: Optional[str] = None


class FuelFillUp(FuelFillUpIn):
    id: str
    totalCost: float


class ServiceRecordIn(BaseModel):
    vehicleId: str
    date: str
    mileage: float = Field(ge=0)
    cost: float = Field(ge=0)
    items: List[str] = Field(default_factory=list)


class ServiceRecord(ServiceRecordIn):
    id: str


@router.post("/fuel", response_model=FuelFillUp)
async def add_fuel(body: FuelFillUpIn):
    rec = {"id": _id(), **body.model_dump(), "totalCost": round(body.litres * body.pricePerLitre, 2)}
    _FUEL.setdefault(body.vehicleId, []).append(rec)
    return rec


@router.get("/fuel", response_model=List[FuelFillUp])
async def list_fuel(vehicleId: str = Query(...)):
    return _FUEL.get(vehicleId, [])


@router.post("/service", response_model=ServiceRecord)
async def add_service(body: ServiceRecordIn):
    rec = {"id": _id(), **body.model_dump()}
    _SERVICE.setdefault(body.vehicleId, []).append(rec)
    return rec


@router.get("/service", response_model=List[ServiceRecord])
async def list_service(vehicleId: str = Query(...)):
    return _SERVICE.get(vehicleId, [])


@router.get("/economy")
async def economy(vehicleId: str = Query(...)):
    fills = sorted(_FUEL.get(vehicleId, []), key=lambda x: x["odometer"])
    out = []
    for i in range(1, len(fills)):
        prev, cur = fills[i - 1], fills[i]
        km = cur["odometer"] - prev["odometer"]
        l100 = (cur["litres"] / km * 100) if km > 0 else None
        out.append({"fillUpId": cur["id"], "date": cur["date"], "km": km, "litres": cur["litres"], "lPer100km": l100})
    return {"vehicleId": vehicleId, "readings": out}


@router.get("/spending")
async def spending(vehicleId: str = Query(...)):
    buckets: Dict[str, float] = {}
    for f in _FUEL.get(vehicleId, []):
        m = f["date"][:7]
        buckets[m] = buckets.get(m, 0) + f["totalCost"]
    for s in _SERVICE.get(vehicleId, []):
        m = s["date"][:7]
        buckets[m] = buckets.get(m, 0) + s["cost"]
    return {"vehicleId": vehicleId, "monthly": [{"month": k, "total": round(v, 2)} for k, v in sorted(buckets.items())]}


@router.get("/tax-export", response_class=PlainTextResponse)
async def tax_export(vehicleId: str = Query(...), businessUsePct: float = Query(100.0, ge=0, le=100)):
    lines = ["type,date,amount,business_use_pct,claimable"]
    for f in _FUEL.get(vehicleId, []):
        claim = round(f["totalCost"] * businessUsePct / 100, 2)
        lines.append(f"fuel,{f['date']},{f['totalCost']},{businessUsePct},{claim}")
    for s in _SERVICE.get(vehicleId, []):
        claim = round(s["cost"] * businessUsePct / 100, 2)
        lines.append(f"service,{s['date']},{s['cost']},{businessUsePct},{claim}")
    return "\n".join(lines) + "\n"
