"""Parts inventory routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel

from app.api.deps import get_current_user, require_write
from app.services.ownership import get_accessible_vehicle
from app.db.session import get_db
from app.models.part import Part, PartMovement
from app.models.user import User
from app.schemas.part import (
    PartCreate,
    PartMovementCreate,
    PartOut,
    PartUpdate,
    ReorderSuggestion,
)
from app.services.sca_parts import get_sca_parts_guide

router = APIRouter(prefix="/vehicles/{vehicle_id}/parts", tags=["parts"])


class SCALookupRequest(BaseModel):
    rego: str = ""
    state: str = "VIC"
    make: str = ""
    model: str = ""
    year: int | None = None
    engine: str = ""


class SCAPart(BaseModel):
    name: str
    sku: str | None = None
    category: str
    service_group: str | None = None
    service_group_key: str | None = None
    brand: str | None = None
    supplier: str | None = None
    unit_cost: float | None = None
    quantity: int = 1
    notes: str | None = None


class SCALookupResponse(BaseModel):
    source: str
    mode: str | None = None
    vehicle: dict
    categories: list[dict]
    parts: list[SCAPart]
    service_groups: list[str] = []
    note: str | None = None
    formatted_with: str | None = None


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


@router.post("/sca-lookup", response_model=SCALookupResponse)
async def sca_lookup(
    vehicle_id: str,
    payload: SCALookupRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """SCA parts-guide for a vehicle (rego + state), AI-formatted (AUT-1792).

    Inventory-tab feature: returns the vehicle's available parts categories,
    normalised, classified into service groups, and tidied by the 9Router
    formatting layer. The client imports parts straight into inventory.
    """
    await get_accessible_vehicle(db, vehicle_id, user)
    return await get_sca_parts_guide(
        db, vehicle_id,
        rego=payload.rego, state=payload.state,
        make=payload.make, model=payload.model,
        year=payload.year, engine=payload.engine,
    )

