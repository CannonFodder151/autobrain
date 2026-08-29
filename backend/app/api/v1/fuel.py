"""Fuel tracker routes."""

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_write
from app.services.events import add_event
from app.services.ownership import get_accessible_vehicle
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.fuel import FuelLog
from app.models.user import User
from app.schemas.fuel import (
    FuelLogCreate,
    FuelLogOut,
    FuelLogUpdate,
    FuelReceiptResult,
    FuelStats,
    FuelPriceQuote,
    SevenElevenPricesOut,
)
from app.services.export import export_fuel_csv, export_zip
from app.services import fuel as fuel_svc
from app.services import fuel_prices as fp_svc
from app.services.odometer import sync_odometer
from app.services.rate_limit import require_ai_rate_limit

router = APIRouter(prefix="/vehicles/{vehicle_id}/fuel", tags=["fuel"])

logger = get_logger(__name__)


@router.get("", response_model=list[FuelLogOut])
async def list_fuel(
    vehicle_id: str,
    fy: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[FuelLog]:
    """List fuel logs, optionally filtered to an Australian financial year
    (e.g. fy=2026 covers 2025-07-01 .. 2026-06-30)."""
    await get_accessible_vehicle(db, vehicle_id, user)
    q = select(FuelLog).where(FuelLog.vehicle_id == vehicle_id)
    if fy:
        q = q.where(FuelLog.fill_date >= date(fy - 1, 7, 1), FuelLog.fill_date <= date(fy, 6, 30))
    rows = await db.scalars(q.order_by(FuelLog.fill_date.desc()))
    return list(rows)


@router.post("", response_model=FuelLogOut, status_code=201)
async def add_fuel(
    vehicle_id: str,
    payload: FuelLogCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> FuelLog:
    vehicle = await get_accessible_vehicle(db, vehicle_id, user)
    total = payload.total_cost if payload.total_cost else round(payload.litres * payload.price_per_litre, 2)
    receipt_id = await fuel_svc.link_receipt(db, vehicle_id, payload.receipt_id)
    log = FuelLog(
        vehicle_id=vehicle_id,
        total_cost=total,
        receipt_id=receipt_id,
        **payload.model_dump(exclude={"total_cost", "receipt_id"}),
    )
    db.add(log)
    await db.flush()
    await fuel_svc.recompute_efficiency(db, vehicle_id)
    await sync_odometer(db, vehicle, payload.odometer_km, fuel_svc.ref_time(log))
    await add_event(
        db,
        vehicle_id,
        "fuel",
        f"Fuel {payload.litres:.1f}L @ {payload.odometer_km:,} km",
        payload.fill_date,
        payload.odometer_km,
        total,
        log.id,
    )
    await db.commit()
    await db.refresh(log)
    from app.workers.tasks import check_due_notifications
    check_due_notifications.delay(vehicle_id)
    return log


@router.patch("/{fuel_id}", response_model=FuelLogOut)
async def update_fuel(
    vehicle_id: str,
    fuel_id: str,
    payload: FuelLogUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> FuelLog:
    await get_accessible_vehicle(db, vehicle_id, user)
    log = await db.get(FuelLog, fuel_id)
    if not log or log.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Fuel log not found")
    data = payload.model_dump(exclude_unset=True)
    if "receipt_id" in data:
        data["receipt_id"] = await fuel_svc.link_receipt(db, vehicle_id, data["receipt_id"])
    if "total_cost" in data and data["total_cost"] is None:
        data.pop("total_cost")
    if data.get("total_cost") is None:
        data["total_cost"] = round(
            data.get("litres", log.litres) * data.get("price_per_litre", log.price_per_litre), 2
        )
    for key, value in data.items():
        setattr(log, key, value)
    if log.odometer_km <= 0:
        raise HTTPException(status_code=422, detail="odometer_km must be positive")
    await fuel_svc.recompute_efficiency(db, vehicle_id)
    await db.flush()
    await sync_odometer(db, await get_accessible_vehicle(db, vehicle_id, user), log.odometer_km, fuel_svc.ref_time(log))
    await db.commit()
    await db.refresh(log)
    return log


@router.delete("/{fuel_id}", status_code=204)
async def delete_fuel(
    vehicle_id: str,
    fuel_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> None:
    await get_accessible_vehicle(db, vehicle_id, user)
    log = await db.get(FuelLog, fuel_id)
    if not log or log.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Fuel log not found")
    await db.delete(log)
    await fuel_svc.recompute_efficiency(db, vehicle_id)
    await db.commit()


@router.get("/stats", response_model=FuelStats)
async def fuel_stats(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await get_accessible_vehicle(db, vehicle_id, user)
    return await fuel_svc.compute_fuel_stats(db, vehicle_id)


@router.get("/export")
async def export_fuel_year(
    vehicle_id: str,
    fy: int | None = Query(default=None),
    fmt: str = Query("csv", pattern="^(csv|zip)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Export fuel records for an Australian financial year (tax purposes).

    fmt=zip bundles the CSV (with an Image column) plus the receipt images.
    """
    vehicle = await get_accessible_vehicle(db, vehicle_id, user)
    fy = fy or fuel_svc.current_fy()
    start = datetime(fy - 1, 7, 1)
    end = datetime(fy, 6, 30, 23, 59, 59)
    logs = list((await db.scalars(
        select(FuelLog).where(
            FuelLog.vehicle_id == vehicle_id,
            FuelLog.fill_date >= start.date(),
            FuelLog.fill_date <= end.date(),
        ).order_by(FuelLog.fill_date)
    )).all())
    content = export_fuel_csv(logs, fy)
    label = vehicle.nickname.replace(" ", "-")
    if fmt == "csv":
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="fuel-{label}-FY{fy-1}-{str(fy)[2:]}.csv"'},
        )
    zipped = export_zip(content, await fuel_svc.receipt_images(logs))
    return Response(
        content=zipped,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="fuel-{label}-FY{fy-1}-{str(fy)[2:]}-with-images.zip"'},
    )


@router.post("/receipt", response_model=FuelReceiptResult, status_code=201)
async def upload_fuel_receipt(
    vehicle_id: str,
    file: UploadFile = File(...),
    ai: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
    _: User = Depends(require_ai_rate_limit),
) -> FuelReceiptResult:
    """Upload a fuel receipt photo.

    With ai=true (paid accounts) the receipt is OCR'd to fill litres and
    price-per-litre. ai=false just stores the photo — the user fills the
    values manually.
    """
    await get_accessible_vehicle(db, vehicle_id, user)
    data = await file.read()
    receipt, url, parsed = await fuel_svc.upload_fuel_receipt(db, vehicle_id, file.filename, file.content_type, data, ai=ai)
    return FuelReceiptResult(
        receipt_id=receipt.id,
        file_url=url,
        vendor=parsed.get("vendor"),
        date=parsed.get("date"),
        litres=parsed.get("litres"),
        price_per_litre=parsed.get("price_per_litre"),
        total_cost=parsed.get("total_cost"),
        currency=parsed.get("currency", "AUD"),
        ai_used=bool(ai and parsed),
    )


@router.get("/prices/7eleven", response_model=SevenElevenPricesOut)
async def seven_eleven_prices(
    vehicle_id: str,
    fuel_type: str = Query(default="U91", pattern="^(E10|U91|U95|U98|Diesel|LPG)$"),
    region: str | None = Query(default=None, description="State/region, e.g. VIC, NSW, QLD, WA, ACT, All"),
    lat: float | None = Query(default=None, description="If set, returns nearest stores instead of cheapest-by-region"),
    lng: float | None = Query(default=None),
    max_results: int = Query(default=5, ge=1, le=25),
    max_km: float | None = Query(default=None, gt=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SevenElevenPricesOut:
    """Accurate 7-Eleven fuel prices (projectzerothree.info) for auto-filling a fill-up.

    Two modes (mutually exclusive — lat/lng wins):
      * cheapest: top-3 prices for `region` + `fuel_type` (default, region=All).
      * nearest: closest stores to (lat,lng) selling `fuel_type`.

    Deterministic + keyless: no AI, no spend. On upstream failure the service
    serves its last good cached snapshot; if none, 503 so the client falls back
    to manual price entry rather than showing a fabricated number.
    """
    await get_accessible_vehicle(db, vehicle_id, user)
    if lat is not None and lng is not None:
        quotes = await fp_svc.nearest_7eleven(lat, lng, fuel_type, max_results=max_results, max_km=max_km)
        mode, use_region = "nearest", None
    else:
        use_region = (region or "All").upper()
        quotes = await fp_svc.cheapest_7eleven(use_region, fuel_type)
        mode = "cheapest"
    data = await fp_svc.fetch_7eleven_prices()
    as_of = None
    if fp_svc._cache["fetched_at"]:
        as_of = datetime.fromtimestamp(fp_svc._cache["fetched_at"], timezone.utc).isoformat()
    return SevenElevenPricesOut(
        source="projectzerothree",
        updated=data.get("updated"),
        as_of=as_of,
        mode=mode,
        fuel_type=fuel_type,
        region=use_region,
        quotes=[FuelPriceQuote(**q) for q in quotes],
    )
