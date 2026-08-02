"""AI diagnostics routes."""

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.v1.vehicles import add_event, _get_owned_vehicle
from app.db.session import get_db
from app.models.diagnostic import Diagnostic
from app.models.service import ServiceRecord
from app.models.user import User
from app.schemas.diagnostic import (
    AddToServiceRequest,
    DiagnosticOut,
    DiagnosticRequest,
    DiagnosticResponse,
)
from app.services.ai_client import run_diagnostics

router = APIRouter(prefix="/vehicles/{vehicle_id}/diagnostics", tags=["diagnostics"])


@router.post("", response_model=DiagnosticResponse)
async def diagnose(
    vehicle_id: str,
    payload: DiagnosticRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DiagnosticResponse:
    vehicle = await _get_owned_vehicle(db, vehicle_id, user)
    context = payload.vehicle_context or {}
    context.setdefault("vehicle", {
        "make": vehicle.make, "model": vehicle.model, "year": vehicle.year,
        "engine": vehicle.engine, "odometer_km": vehicle.odometer_km,
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
    return DiagnosticResponse(**result)


@router.get("", response_model=list[DiagnosticOut])
async def list_diagnostics(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Diagnostic]:
    await _get_owned_vehicle(db, vehicle_id, user)
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
    user: User = Depends(get_current_user),
) -> Diagnostic:
    await _get_owned_vehicle(db, vehicle_id, user)
    diag = await db.get(Diagnostic, diagnostic_id)
    if not diag or diag.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Diagnostic not found")
    if diag.added_to_service:
        raise HTTPException(status_code=409, detail="Already added to a service")
    service = ServiceRecord(
        vehicle_id=vehicle_id,
        service_date=(payload.service_date.date() if payload.service_date else date.today()),
        odometer_km=0,
        service_type="repair",
        description=f"From diagnostic: {diag.summary or diag.symptoms[:200]}",
        cost=diag.estimated_cost or 0.0,
        notes=payload.notes,
    )
    db.add(service)
    await db.flush()
    diag.added_to_service = True
    diag.linked_service_id = service.id
    await add_event(
        db, vehicle_id, "service",
        f"Repair queued from diagnostic: {diag.summary or 'diagnostic'}",
        service.service_date, service.odometer_km, service.cost, service.id,
    )
    await db.commit()
    await db.refresh(diag)
    return diag
