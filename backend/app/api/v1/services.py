"""Service routes: CRUD (with items/status), AI prediction, PDF/CSV export."""

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.api.v1.vehicles import add_event, _get_owned_vehicle
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.service import ServiceItem, ServiceRecord
from app.models.user import User
from app.models.vehicle import VehicleEvent
from app.schemas.service import (
    ServiceCreate,
    ServiceOut,
    ServicePredictionRequest,
    ServicePredictionResponse,
    ServiceUpdate,
)
from app.services.ai_client import predict_service
from app.services.export import export_service_history_csv, export_service_history_pdf

logger = get_logger(__name__)
router = APIRouter(prefix="/vehicles/{vehicle_id}/services", tags=["services"])


def _load_options() -> selectinload:
    return selectinload(ServiceRecord.items)


async def _service_or_404(db: AsyncSession, vehicle_id: str, service_id: str) -> ServiceRecord:
    record = await db.scalar(
        select(ServiceRecord)
        .options(_load_options())
        .where(ServiceRecord.id == service_id, ServiceRecord.vehicle_id == vehicle_id)
    )
    if not record:
        raise HTTPException(status_code=404, detail="Service not found")
    return record


async def _ensure_completed_event(db: AsyncSession, record: ServiceRecord) -> None:
    if record.status != "completed":
        return
    existing = await db.scalar(
        select(VehicleEvent).where(VehicleEvent.source_id == record.id)
    )
    if not existing:
        await add_event(
            db, record.vehicle_id, "service",
            f"{record.service_type.title()} service @ {record.odometer_km:,} km",
            record.completed_date or record.service_date,
            record.odometer_km, record.cost, record.id,
        )


@router.get("", response_model=list[ServiceOut])
async def list_services(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ServiceRecord]:
    await _get_owned_vehicle(db, vehicle_id, user)
    rows = await db.scalars(
        select(ServiceRecord)
        .options(_load_options())
        .where(ServiceRecord.vehicle_id == vehicle_id)
        .order_by(ServiceRecord.service_date.desc())
    )
    return list(rows)


@router.post("", response_model=ServiceOut, status_code=201)
async def create_service(
    vehicle_id: str,
    payload: ServiceCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ServiceRecord:
    await _get_owned_vehicle(db, vehicle_id, user)
    data = payload.model_dump(exclude={"items", "steps"})
    if payload.steps:
        data["steps"] = json.dumps(payload.steps)
    record = ServiceRecord(vehicle_id=vehicle_id, **data)
    record.status = payload.status
    if record.status == "completed":
        record.completed_date = record.completed_date or record.service_date
    db.add(record)
    await db.flush()
    for item in payload.items:
        db.add(ServiceItem(service_id=record.id, **item.model_dump()))
    await db.flush()
    await _ensure_completed_event(db, record)
    await db.commit()
    await db.refresh(record)
    return record


@router.get("/export")
async def export(
    vehicle_id: str,
    fmt: str = Query("csv", pattern="^(csv|pdf)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    vehicle = await _get_owned_vehicle(db, vehicle_id, user)
    rows = await db.scalars(
        select(ServiceRecord)
        .options(_load_options())
        .where(
            ServiceRecord.vehicle_id == vehicle_id,
            ServiceRecord.status == "completed",  # future services excluded
        )
        .order_by(ServiceRecord.service_date)
    )
    records = list(rows)
    label = f"{vehicle.make or ''} {vehicle.model or ''}".strip() or vehicle.nickname
    if fmt == "csv":
        content = export_service_history_csv(records, label)
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="service-history-{vehicle.id}.csv"'},
        )
    pdf = export_service_history_pdf(records, label)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="service-history-{vehicle.id}.pdf"'},
    )


@router.get("/{service_id}", response_model=ServiceOut)
async def get_service(
    vehicle_id: str,
    service_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ServiceRecord:
    await _get_owned_vehicle(db, vehicle_id, user)
    return await _service_or_404(db, vehicle_id, service_id)


@router.patch("/{service_id}", response_model=ServiceOut)
async def update_service(
    vehicle_id: str,
    service_id: str,
    payload: ServiceUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ServiceRecord:
    await _get_owned_vehicle(db, vehicle_id, user)
    record = await _service_or_404(db, vehicle_id, service_id)

    updates = payload.model_dump(exclude_unset=True)
    items = updates.pop("items", None)
    steps = updates.pop("steps", None)
    if steps is not None:
        updates["steps"] = json.dumps(steps)
    for key, value in updates.items():
        setattr(record, key, value)

    if record.status == "completed" and record.completed_date is None:
        record.completed_date = record.service_date

    if items is not None:
        await db.execute(
            ServiceItem.__table__.delete().where(ServiceItem.service_id == record.id)
        )
        await db.flush()
        for item in items:
            db.add(ServiceItem(service_id=record.id, **item))

    await db.flush()
    await _ensure_completed_event(db, record)
    await db.commit()
    await db.refresh(record)
    return record


@router.delete("/{service_id}", status_code=204)
async def delete_service(
    vehicle_id: str,
    service_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    await _get_owned_vehicle(db, vehicle_id, user)
    record = await _service_or_404(db, vehicle_id, service_id)
    await db.delete(record)
    await db.commit()


@router.post("/predict", response_model=ServicePredictionResponse)
async def predict(
    payload: ServicePredictionRequest,
) -> ServicePredictionResponse:
    """AI service prediction using history + odometer + make/model schedule."""
    result = await predict_service(payload.model_dump())
    if not result:
        raise HTTPException(status_code=503, detail="Prediction engine unavailable")
    return ServicePredictionResponse(**result)
