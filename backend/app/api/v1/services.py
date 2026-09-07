"""Service routes: CRUD (with items/status), AI prediction, PDF/CSV export."""

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_write
from app.services.ownership import get_accessible_vehicle, require_ai_vehicle
from app.core.logging import get_logger
from app.core.storage import get_object
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
from app.services.export import export_service_history_csv, export_service_history_pdf, export_zip
from app.services.rate_limit import require_ai_rate_limit
from app.services.service_records import (
    finalize_service_side_effects,
    list_completed_services,
    load_options,
    queue_due_notification,
    reconcile_part_stock,
    service_or_404,
)
from app.workers.tasks import queue_embedding

logger = get_logger(__name__)
router = APIRouter(prefix="/vehicles/{vehicle_id}/services", tags=["services"])


@router.get("", response_model=list[ServiceOut])
async def list_services(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ServiceRecord]:
    await get_accessible_vehicle(db, vehicle_id, user)
    rows = await db.scalars(
        select(ServiceRecord)
        .options(load_options())
        .where(ServiceRecord.vehicle_id == vehicle_id)
        .order_by(ServiceRecord.service_date.desc())
    )
    return list(rows)


@router.post("", response_model=ServiceOut, status_code=201)
async def create_service(
    vehicle_id: str,
    payload: ServiceCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> ServiceRecord:
    await get_accessible_vehicle(db, vehicle_id, user)
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
    await finalize_service_side_effects(db, vehicle_id, record, payload.items)
    await db.commit()
    await db.refresh(record)
    await queue_due_notification(db, vehicle_id, record)
    queue_embedding("service", str(record.id))
    return record


@router.get("/export")
async def export(
    vehicle_id: str,
    fmt: str = Query("csv", pattern="^(csv|pdf|zip)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    vehicle = await get_accessible_vehicle(db, vehicle_id, user)
    records = await list_completed_services(db, vehicle_id)
    label = f"{vehicle.make or ''} {vehicle.model or ''}".strip() or vehicle.nickname
    if fmt == "csv":
        content = export_service_history_csv(records, label)
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="service-history-{vehicle.id}.csv"'},
        )
    if fmt == "pdf":
        pdf = export_service_history_pdf(records, label, vehicle.rego or "")
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="service-history-{vehicle.id}.pdf"'},
        )
    # fmt == "zip": CSV (with Image column) + the receipt/scan images
    content = export_service_history_csv(records, label)
    images: dict[str, bytes] = {}
    for r in records:
        for k in (r.photo_keys or []):
            try:
                images[k.rsplit("/", 1)[-1]] = await get_object(k)
            except Exception:
                continue
    zipped = export_zip(content, images)
    return Response(
        content=zipped,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="service-history-{vehicle.id}-with-images.zip"'},
    )


@router.get("/{service_id}", response_model=ServiceOut)
async def get_service(
    vehicle_id: str,
    service_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ServiceRecord:
    await get_accessible_vehicle(db, vehicle_id, user)
    return await service_or_404(db, vehicle_id, service_id)


@router.patch("/{service_id}", response_model=ServiceOut)
async def update_service(
    vehicle_id: str,
    service_id: str,
    payload: ServiceUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> ServiceRecord:
    await get_accessible_vehicle(db, vehicle_id, user)
    record = await service_or_404(db, vehicle_id, service_id)

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
    fresh_items = list((await db.scalars(
        select(ServiceItem).where(ServiceItem.service_id == record.id)
    )).all())
    await finalize_service_side_effects(db, vehicle_id, record, fresh_items)
    await db.commit()
    await db.refresh(record)
    await queue_due_notification(db, vehicle_id, record)
    queue_embedding("service", str(record.id))
    return record


@router.delete("/{service_id}", status_code=204)
async def delete_service(
    vehicle_id: str,
    service_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> None:
    await get_accessible_vehicle(db, vehicle_id, user)
    record = await service_or_404(db, vehicle_id, service_id)
    await reconcile_part_stock(db, vehicle_id, service_id, [], deduct=False)
    await db.execute(
        VehicleEvent.__table__.delete().where(VehicleEvent.source_id == service_id)
    )
    had_due = record.next_due_km is not None or record.next_due_date is not None
    await db.delete(record)
    await db.commit()
    if had_due:
        from app.workers.tasks import fire_and_forget, check_due_notifications
        fire_and_forget(check_due_notifications, vehicle_id)


@router.post("/predict", response_model=ServicePredictionResponse)
async def predict(
    vehicle_id: str,
    payload: ServicePredictionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    _: User = Depends(require_ai_rate_limit),
) -> ServicePredictionResponse:
    """AI service prediction using ALL past services + odometer + schedule.

    The full completed-service history is sent to the AI so the estimate is
    derived from how this vehicle is actually maintained, not just the last
    service or a generic manufacturer schedule.
    """
    vehicle = await get_accessible_vehicle(db, vehicle_id, user)
    await require_ai_vehicle(db, vehicle, user)
    history = await list_completed_services(db, vehicle_id)
    data = payload.model_dump()
    data["make"] = data["make"] or vehicle.make or ""
    data["model"] = data["model"] or vehicle.model or ""
    data["year"] = data["year"] or vehicle.year or date.today().year
    data["vehicle_type"] = vehicle.vehicle_type or "car"
    if not data.get("odometer_km"):
        data["odometer_km"] = vehicle.odometer_km or 0
    data["service_history"] = [
        {
            "service_date": s.service_date.isoformat(),
            "odometer_km": s.odometer_km,
            "service_type": s.service_type,
            "description": s.description,
        }
        for s in history
    ]
    result = await predict_service(data)
    if not result:
        raise HTTPException(status_code=503, detail="Prediction engine unavailable")
    return ServicePredictionResponse(**result)
