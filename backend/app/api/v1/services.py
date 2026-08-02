"""Service routes: CRUD, AI prediction, PDF/CSV export."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.v1.vehicles import add_event, _get_owned_vehicle
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.service import ServiceItem, ServiceRecord
from app.models.user import User
from app.models.vehicle import Vehicle
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


@router.get("", response_model=list[ServiceOut])
async def list_services(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ServiceRecord]:
    await _get_owned_vehicle(db, vehicle_id, user)
    rows = await db.scalars(
        select(ServiceRecord)
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
    record = ServiceRecord(vehicle_id=vehicle_id, **payload.model_dump(exclude={"items"}))
    db.add(record)
    await db.flush()
    for item in payload.items:
        db.add(ServiceItem(service_id=record.id, **item.model_dump()))
    await add_event(
        db,
        vehicle_id,
        "service",
        f"{record.service_type.title()} service @ {record.odometer_km:,} km",
        record.service_date,
        record.odometer_km,
        record.cost,
        record.id,
    )
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
        .where(ServiceRecord.vehicle_id == vehicle_id)
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
    record = await db.get(ServiceRecord, service_id)
    if not record or record.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Service not found")
    return record


@router.patch("/{service_id}", response_model=ServiceOut)
async def update_service(
    vehicle_id: str,
    service_id: str,
    payload: ServiceUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ServiceRecord:
    await _get_owned_vehicle(db, vehicle_id, user)
    record = await db.get(ServiceRecord, service_id)
    if not record or record.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Service not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(record, key, value)
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
    record = await db.get(ServiceRecord, service_id)
    if not record or record.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Service not found")
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

