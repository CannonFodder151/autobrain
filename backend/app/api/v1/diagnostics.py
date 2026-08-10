"""AI diagnostics routes."""

import json
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_write
from app.services.ownership import get_accessible_vehicle, require_ai_vehicle
from app.workers.tasks import queue_embedding
from app.db.session import get_db
from app.models.diagnostic import Diagnostic
from app.models.service import ServiceItem, ServiceRecord
from app.models.user import User
from app.schemas.diagnostic import (
    AddToServiceRequest,
    DiagnosticOut,
    DiagnosticRequest,
    DiagnosticResponse,
)
from app.services.ai_client import run_diagnostics

router = APIRouter(prefix="/vehicles/{vehicle_id}/diagnostics", tags=["diagnostics"])


async def _auto_resolve(db: AsyncSession, diagnostic_id: str | None) -> None:
    """Mark a diagnostic resolved when its linked service is completed."""
    if not diagnostic_id:
        return
    diag = await db.get(Diagnostic, diagnostic_id)
    if not diag or diag.status == "resolved":
        return
    service = await db.get(ServiceRecord, diag.linked_service_id) if diag.linked_service_id else None
    if service and service.status == "completed":
        diag.status = "resolved"
        diag.resolved_at = datetime.now(timezone.utc)


@router.post("", response_model=DiagnosticResponse)
async def diagnose(
    vehicle_id: str,
    payload: DiagnosticRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DiagnosticResponse:
    vehicle = await get_accessible_vehicle(db, vehicle_id, user)
    await require_ai_vehicle(db, vehicle, user)
    context = payload.vehicle_context or {}
    context.setdefault("vehicle", {
        "make": vehicle.make, "model": vehicle.model, "year": vehicle.year,
        "engine": vehicle.engine, "odometer_km": vehicle.odometer_km,
        "vehicle_type": vehicle.vehicle_type,
    })
    result = await run_diagnostics({"symptoms": payload.symptoms, **context, "obd_codes": payload.obd_codes})
    if not result:
        raise HTTPException(status_code=503, detail="Diagnostics engine unavailable")
    record = Diagnostic(
        vehicle_id=vehicle_id,
        symptoms=payload.symptoms,
        ai_response=json.dumps(result),
        summary=result.get("summary"),
        severity=result.get("severity"),
        estimated_cost=result.get("estimated_cost"),
        parts_needed=json.dumps(result.get("parts_needed", [])),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    queue_embedding("diagnostic", str(record.id))
    return DiagnosticResponse(**result)


@router.get("", response_model=list[DiagnosticOut])
async def list_diagnostics(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Diagnostic]:
    await get_accessible_vehicle(db, vehicle_id, user)
    rows = await db.scalars(
        select(Diagnostic)
        .where(Diagnostic.vehicle_id == vehicle_id)
        .order_by(Diagnostic.created_at.desc())
    )
    return list(rows)


@router.post("/{diagnostic_id}/add-to-service", response_model=DiagnosticOut)
async def add_to_service(
    vehicle_id: str,
    diagnostic_id: str,
    payload: AddToServiceRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> Diagnostic:
    vehicle = await get_accessible_vehicle(db, vehicle_id, user)
    diag = await db.get(Diagnostic, diagnostic_id)
    if not diag or diag.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Diagnostic not found")
    if diag.added_to_service:
        raise HTTPException(status_code=409, detail="Already added to a service")

    ai = json.loads(diag.ai_response) if diag.ai_response else {}
    steps = ai.get("recommended_actions", []) or []
    parts: list[dict] = []
    for item in ai.get("items", []):
        for p in item.get("parts", []) or []:
            if p.get("name") and p not in parts:
                parts.append(p)
    if not parts:
        parts = [{"name": n, "part_number": None} for n in (ai.get("parts_needed", []) or [])]

    # A queued diagnostic becomes a FUTURE (scheduled) service.
    service = ServiceRecord(
        vehicle_id=vehicle_id,
        service_date=(payload.service_date.date() if payload.service_date else date.today()),
        odometer_km=vehicle.odometer_km or 0,
        service_type="repair",
        description=f"From diagnostic: {diag.summary or diag.symptoms[:200]}",
        cost=diag.estimated_cost or 0.0,
        notes=payload.notes,
        status="scheduled",
        steps=json.dumps(steps) if steps else None,
    )
    db.add(service)
    await db.flush()
    for p in parts:
        db.add(
            ServiceItem(
                service_id=service.id,
                name=p.get("name", "Part"),
                quantity=1,
                kind="part",
                part_no=p.get("part_number"),
            )
        )
    diag.added_to_service = True
    diag.linked_service_id = service.id
    await db.commit()
    await db.refresh(diag)
    queue_embedding("service", str(service.id))
    queue_embedding("diagnostic", str(diag.id))
    return diag


@router.post("/{diagnostic_id}/resolve", response_model=DiagnosticOut)
async def resolve_diagnostic(
    vehicle_id: str,
    diagnostic_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> Diagnostic:
    """Mark a diagnostic as resolved once the issue is fixed."""
    await get_accessible_vehicle(db, vehicle_id, user)
    diag = await db.get(Diagnostic, diagnostic_id)
    if not diag or diag.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Diagnostic not found")
    diag.status = "resolved"
    diag.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(diag)
    return diag


@router.delete("/{diagnostic_id}", status_code=204)
async def delete_diagnostic(
    vehicle_id: str,
    diagnostic_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> None:
    """Delete a diagnostic once the issue is resolved."""
    await get_accessible_vehicle(db, vehicle_id, user)
    diag = await db.get(Diagnostic, diagnostic_id)
    if not diag or diag.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Diagnostic not found")
    await db.delete(diag)
    await db.commit()

