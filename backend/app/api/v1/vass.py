from fastapi import APIRouter, HTTPException, Path

from app.schemas.vass import (
    VehicleLookupIn,
    VehicleLookupOut,
    VinDecodeOut,
    ChecklistIn,
    ChecklistOut,
    ComplianceResultIn,
    ComplianceResultOut,
)
from app.services.vass import lookup_vehicle, decode_vin, generate_checklist, aggregate_results

router = APIRouter()


@router.post("/lookup", response_model=VehicleLookupOut)
async def vehicle_lookup(body: VehicleLookupIn):
    v = lookup_vehicle(body.make, body.model, body.year)
    if not v:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    return VehicleLookupOut(
        make=v.make,
        model=v.model,
        year=v.year,
        base_vehicle_id=v.base_vehicle_id,
        vin_prefix=v.vin_prefix,
        compliance_status=v.compliance_status,
    )


@router.get("/vin/{vin}/decode", response_model=VinDecodeOut)
async def vin_decode(vin: str = Path(..., min_length=1, max_length=17)):
    info = decode_vin(vin)
    if not info.valid and info.errors:
        # still return 200 with valid False per typical API design; or 400. follow requirement loosely
        pass
    return VinDecodeOut(**info.__dict__)


@router.post("/checklist", response_model=ChecklistOut)
async def compliance_checklist(body: ChecklistIn):
    items = generate_checklist(body.vehicle_id, body.modifications)
    return ChecklistOut(
        vehicle_id=body.vehicle_id,
        items=[i.__dict__ for i in items],
        total=len(items),
        passed=sum(1 for i in items if i.status == "pass"),
        failed=sum(1 for i in items if i.status == "fail"),
        pending=sum(1 for i in items if i.status == "pending"),
    )


@router.post("/results", response_model=ComplianceResultOut)
async def compliance_results(body: ComplianceResultIn):
    res = aggregate_results(body.vehicle_id, body.results)
    return ComplianceResultOut(**res.__dict__)
