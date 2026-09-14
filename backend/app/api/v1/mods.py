"""Modification tracker routes."""

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_ai, require_write
from app.services.events import add_event
from app.services.ownership import get_accessible_vehicle
from app.workers.tasks import queue_embedding
from app.core.storage import get_object
from app.db.session import get_db
from app.models.mod import Modification
from app.models.user import User
from app.schemas.mod import (
    ModCreate,
    ModImpactRequest,
    ModImpactResponse,
    ModOut,
    ModUpdate,
)
from app.services.ai_client import mod_impact
from app.services.export import export_build_sheet_csv, export_build_sheet_pdf, export_zip
from app.services.rate_limit import require_ai_rate_limit

router = APIRouter(prefix="/vehicles/{vehicle_id}/mods", tags=["mods"])


@router.get("", response_model=list[ModOut])
async def list_mods(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Modification]:
    await get_accessible_vehicle(db, vehicle_id, user)
    rows = await db.scalars(
        select(Modification)
        .where(Modification.vehicle_id == vehicle_id)
        .order_by(Modification.created_at.desc())
    )
    return list(rows)


@router.post("", response_model=ModOut, status_code=201)
async def create_mod(
    vehicle_id: str,
    payload: ModCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> Modification:
    await get_accessible_vehicle(db, vehicle_id, user)
    mod = Modification(vehicle_id=vehicle_id, **payload.model_dump())
    db.add(mod)
    await db.flush()
    if mod.install_date:
        await add_event(
            db, vehicle_id, "mod",
            f"Mod installed: {mod.name}",
            mod.install_date, mod.odometer_km, mod.cost, mod.id,
        )
    await db.commit()
    await db.refresh(mod)
    queue_embedding("modification", str(mod.id))
    return mod


@router.patch("/{mod_id}", response_model=ModOut)
async def update_mod(
    vehicle_id: str,
    mod_id: str,
    payload: ModUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> Modification:
    await get_accessible_vehicle(db, vehicle_id, user)
    mod = await db.get(Modification, mod_id)
    if not mod or mod.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Modification not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(mod, key, value)
    await db.commit()
    await db.refresh(mod)
    queue_embedding("modification", str(mod.id))
    return mod


@router.delete("/{mod_id}", status_code=204)
async def delete_mod(
    vehicle_id: str,
    mod_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> None:
    await get_accessible_vehicle(db, vehicle_id, user)
    mod = await db.get(Modification, mod_id)
    if not mod or mod.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Modification not found")
    await db.delete(mod)
    await db.commit()


@router.post("/impact", response_model=ModImpactResponse)
async def get_impact(
    payload: ModImpactRequest,
    _user: User = Depends(require_ai),
    _: User = Depends(require_ai_rate_limit),
) -> ModImpactResponse:
    """AI summary of a modification's impact on performance and value."""
    data = payload.model_dump()
    if data.get("vehicle") and not data["vehicle"].get("vehicle_type"):
        data["vehicle"]["vehicle_type"] = "car"
    result = await mod_impact(data)
    if not result:
        raise HTTPException(status_code=503, detail="Mod impact engine unavailable")
    return ModImpactResponse(**result)


@router.get("/export")
async def export_build_sheet(
    vehicle_id: str,
    fmt: str = "csv",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    vehicle = await get_accessible_vehicle(db, vehicle_id, user)
    rows = await db.scalars(
        select(Modification).where(Modification.vehicle_id == vehicle_id).order_by(Modification.created_at)
    )
    mods = list(rows)
    label = f"{vehicle.make or ''} {vehicle.model or ''}".strip() or vehicle.nickname
    if fmt == "csv":
        content = export_build_sheet_csv(mods, label)
        return Response(
            content=content, media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="build-sheet-{vehicle.id}.csv"'},
        )
    if fmt == "pdf":
        pdf = export_build_sheet_pdf(mods, label, vehicle.rego or "")
        return Response(
            content=pdf, media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="build-sheet-{vehicle.id}.pdf"'},
        )
    # fmt == "zip": CSV (with Image column) + the mod photos
    content = export_build_sheet_csv(mods, label)
    images: dict[str, bytes] = {}
    for m in mods:
        for k in (m.photo_keys or []):
            try:
                images[k.rsplit("/", 1)[-1]] = await get_object(k)
            except Exception:
                continue
    zipped = export_zip(content, images)
    return Response(
        content=zipped, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="build-sheet-{vehicle.id}-with-images.zip"'},
    )
