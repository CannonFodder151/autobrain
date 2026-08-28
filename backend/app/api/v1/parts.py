"""Parts inventory routes."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_write
from app.services.ownership import get_accessible_vehicle
from app.db.session import get_db
from app.models.part import Part, PartMovement
from app.models.user import User
from app.models.vehicle import Vehicle
from app.schemas.part import (
    PartCreate,
    PartMovementCreate,
    PartOut,
    PartUpdate,
    ReorderSuggestion,
)
from app.services import parts_guide

router = APIRouter(prefix="/vehicles/{vehicle_id}/parts", tags=["parts"])


class SCALookupRequest(BaseModel):
    rego: str | None = None
    state: str | None = None
    make: str | None = None
    model: str | None = None
    year: int | None = None
    refresh: bool = False


class ServicePartsRequest(BaseModel):
    service_type: str = "scheduled"
    rego: str | None = None
    state: str | None = None
    refresh: bool = False


@router.get("", response_model=list[PartOut])
async def list_parts(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Part]:
    await get_accessible_vehicle(db, vehicle_id, user)
    rows = await db.scalars(
        select(Part).where(Part.vehicle_id == vehicle_id).order_by(Part.name)
    )
    return list(rows)


@router.post("", response_model=PartOut, status_code=201)
async def create_part(
    vehicle_id: str,
    payload: PartCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> Part:
    await get_accessible_vehicle(db, vehicle_id, user)
    part = Part(vehicle_id=vehicle_id, **payload.model_dump())
    db.add(part)
    await db.flush()
    db.add(PartMovement(part_id=part.id, delta=payload.quantity, reason="purchase"))
    await db.commit()
    await db.refresh(part)
    return part


@router.patch("/{part_id}", response_model=PartOut)
async def update_part(
    vehicle_id: str,
    part_id: str,
    payload: PartUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> Part:
    await get_accessible_vehicle(db, vehicle_id, user)
    part = await db.get(Part, part_id)
    if not part or part.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Part not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(part, key, value)
    await db.commit()
    await db.refresh(part)
    return part


@router.post("/{part_id}/movement", response_model=PartOut)
async def add_movement(
    vehicle_id: str,
    part_id: str,
    payload: PartMovementCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> Part:
    await get_accessible_vehicle(db, vehicle_id, user)
    part = await db.get(Part, part_id)
    if not part or part.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Part not found")
    if part.quantity + payload.delta < 0:
        raise HTTPException(status_code=400, detail="Insufficient stock")
    part.quantity += payload.delta
    db.add(
        PartMovement(
            part_id=part_id, delta=payload.delta,
            reason=payload.reason, service_id=payload.service_id,
        )
    )
    await db.commit()
    await db.refresh(part)
    return part


@router.delete("/{part_id}", status_code=204)
async def delete_part(
    vehicle_id: str,
    part_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> None:
    await get_accessible_vehicle(db, vehicle_id, user)
    part = await db.get(Part, part_id)
    if not part or part.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Part not found")
    await db.delete(part)
    await db.commit()


@router.get("/reorder-suggestions", response_model=list[ReorderSuggestion])
async def reorder_suggestions(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ReorderSuggestion]:
    await get_accessible_vehicle(db, vehicle_id, user)
    rows = await db.scalars(
        select(Part).where(
            Part.vehicle_id == vehicle_id,
            Part.quantity <= Part.min_quantity,
        )
    )
    suggestions = []
    for part in rows:
        suggested = max(part.min_quantity * 2 - part.quantity, 1)
        suggestions.append(
            ReorderSuggestion(
                part_id=part.id,
                name=part.name,
                quantity=part.quantity,
                min_quantity=part.min_quantity,
                suggested_order_qty=suggested,
                reason=f"Stock ({part.quantity}) at or below reorder point ({part.min_quantity})",
            )
        )
    return suggestions


@router.get("/sca-lookup", response_model=dict[str, Any])
async def sca_lookup(
    vehicle_id: str,
    req: SCALookupRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Lookup Supercheap Auto parts categories for the given vehicle.

    Returns Inventory-formatted parts with SCA categories normalised and
    ready for the inventory tab. Uses rego+state or make/model/year.
    """
    await get_accessible_vehicle(db, vehicle_id, user)
    vehicle = await db.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    make = req.make or vehicle.make or ""
    model = req.model or vehicle.model or ""
    year = req.year or vehicle.year

    result = await parts_guide.lookup_sca_parts(
        db, rego=req.rego, state=req.state, make=make, model=model,
        year=year, vehicle_type=vehicle.vehicle_type, refresh=req.refresh,
    )
    return result


@router.post("/suggest-for-service", response_model=dict[str, Any])
async def suggest_parts_for_service(
    vehicle_id: str,
    payload: ServicePartsRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Get prefill parts for an AI-suggested service.

    Preference order:
      1. Parts already in inventory whose category matches the service.
      2. SCA suggestions for that service type (cleaned/normalised).

    Returns ServiceItemIn-like items ready to attach to a scheduled service.
    """
    await get_accessible_vehicle(db, vehicle_id, user)
    vehicle = await db.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    result = await parts_guide.suggest_service_parts(
        db, vehicle_id=vehicle_id,
        make=vehicle.make or "", model=vehicle.model or "", year=vehicle.year,
        service_type=payload.service_type,
        rego=vehicle.rego, state=payload.state,
        refresh=payload.refresh,
    )
    return result