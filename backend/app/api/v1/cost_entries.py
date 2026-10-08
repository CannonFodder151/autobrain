"""Cost tracking routes: CRUD, dashboard analytics, and export."""

import csv
import io
from collections import defaultdict
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_write
from app.services.ownership import get_accessible_vehicle
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.cost_entry import CostCategory, CostEntry
from app.models.receipt import Receipt
from app.models.user import User
from app.schemas.cost_entry import (
    BudgetCreate,
    BudgetOut,
    CostDashboard,
    CostEntryCreate,
    CostEntryOut,
    CostEntryUpdate,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/vehicles/{vehicle_id}/cost-entries", tags=["cost-entries"])


@router.post("", response_model=CostEntryOut, status_code=201)
async def create_cost_entry(
    vehicle_id: str,
    payload: CostEntryCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> CostEntry:
    """Create a new cost entry for a vehicle."""
    await get_accessible_vehicle(db, vehicle_id, user)

    if payload.receipt_id:
        receipt = await db.get(Receipt, payload.receipt_id)
        if not receipt or receipt.vehicle_id != vehicle_id:
            raise HTTPException(status_code=404, detail="Receipt not found for this vehicle")

    entry = CostEntry(vehicle_id=vehicle_id, **payload.model_dump())
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.get("", response_model=list[CostEntryOut])
async def list_cost_entries(
    vehicle_id: str,
    category: CostCategory | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[CostEntry]:
    """List cost entries for a vehicle with optional filters."""
    await get_accessible_vehicle(db, vehicle_id, user)

    stmt = select(CostEntry).where(CostEntry.vehicle_id == vehicle_id)

    if category:
        stmt = stmt.where(CostEntry.category == category)
    if date_from:
        stmt = stmt.where(CostEntry.date >= date_from)
    if date_to:
        stmt = stmt.where(CostEntry.date <= date_to)

    stmt = stmt.order_by(CostEntry.date.desc(), CostEntry.created_at.desc())
    return list((await db.scalars(stmt)).all())


@router.get("/dashboard", response_model=CostDashboard)
async def cost_dashboard(
    vehicle_id: str,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CostDashboard:
    """Get cost dashboard analytics for a vehicle."""
    await get_accessible_vehicle(db, vehicle_id, user)

    stmt = select(CostEntry).where(CostEntry.vehicle_id == vehicle_id)
    if date_from:
        stmt = stmt.where(CostEntry.date >= date_from)
    if date_to:
        stmt = stmt.where(CostEntry.date <= date_to)

    entries = list((await db.scalars(stmt)).all())

    total_spent = sum(e.amount for e in entries)

    # Category breakdown
    cat_totals: dict[CostCategory, float] = defaultdict(float)
    cat_counts: dict[CostCategory, int] = defaultdict(int)
    for e in entries:
        cat_totals[e.category] += e.amount
        cat_counts[e.category] += 1

    category_breakdown = [
        {"category": cat, "total": round(total, 2), "count": cat_counts[cat]}
        for cat, total in sorted(cat_totals.items(), key=lambda x: x[1], reverse=True)
    ]

    # Track-day specific metrics
    track_day_entries = [e for e in entries if e.category == CostCategory.TRACK_DAY]
    track_days_count = len(track_day_entries)
    total_laps = sum(e.laps_completed or 0 for e in track_day_entries)

    cost_per_track_day = None
    cost_per_lap = None
    if track_days_count > 0:
        track_day_total = sum(e.amount for e in track_day_entries)
        cost_per_track_day = round(track_day_total / track_days_count, 2)
    if total_laps > 0:
        track_day_total = sum(e.amount for e in track_day_entries)
        cost_per_lap = round(track_day_total / total_laps, 2)

    # Monthly trend
    monthly: dict[str, float] = defaultdict(float)
    for e in entries:
        key = e.date.strftime("%Y-%m")
        monthly[key] += e.amount

    monthly_trend = [
        {"month": k, "total": round(v, 2)} for k, v in sorted(monthly.items())
    ]

    # Budget vs actual (if date_from/date_to covers a month, or use current month)
    budget_vs_actual = None
    # Could be extended with a budget model if needed

    return CostDashboard(
        total_spent=round(total_spent, 2),
        category_breakdown=category_breakdown,
        cost_per_track_day=cost_per_track_day,
        cost_per_lap=cost_per_lap,
        track_days_count=track_days_count,
        total_laps=total_laps,
        monthly_trend=monthly_trend,
        budget_vs_actual=budget_vs_actual,
    )


@router.get("/summary")
async def cost_summary(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Quick summary for UI badges."""
    await get_accessible_vehicle(db, vehicle_id, user)

    # Total all-time
    total_result = await db.execute(
        select(func.sum(CostEntry.amount)).where(CostEntry.vehicle_id == vehicle_id)
    )
    total = total_result.scalar() or 0.0

    # Current month
    today = date.today()
    month_start = today.replace(day=1)
    month_result = await db.execute(
        select(func.sum(CostEntry.amount)).where(
            CostEntry.vehicle_id == vehicle_id,
            CostEntry.date >= month_start,
        )
    )
    this_month = month_result.scalar() or 0.0

    # Track days count
    td_result = await db.execute(
        select(func.count(CostEntry.id)).where(
            CostEntry.vehicle_id == vehicle_id,
            CostEntry.category == CostCategory.TRACK_DAY,
        )
    )
    track_days = td_result.scalar() or 0

    return {
        "total_spent": round(total, 2),
        "this_month": round(this_month, 2),
        "track_days": track_days,
    }


@router.get("/export")
async def export_cost_entries(
    vehicle_id: str,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """CSV export of cost entries for a vehicle."""
    await get_accessible_vehicle(db, vehicle_id, user)

    stmt = select(CostEntry).where(CostEntry.vehicle_id == vehicle_id)
    if date_from:
        stmt = stmt.where(CostEntry.date >= date_from)
    if date_to:
        stmt = stmt.where(CostEntry.date <= date_to)
    stmt = stmt.order_by(CostEntry.date)

    entries = list((await db.scalars(stmt)).all())

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Date", "Category", "Amount", "Currency", "Odometer (km)",
        "Description", "Vendor", "Track Name", "Laps", "Receipt ID"
    ])
    for e in entries:
        writer.writerow([
            e.date,
            e.category.value,
            e.amount,
            e.currency,
            e.odometer_km or "",
            e.description or "",
            e.vendor or "",
            e.track_name or "",
            e.laps_completed or "",
            e.receipt_id or "",
        ])

    content = b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")
    vehicle = await db.get(user.vehicles[0].__class__, vehicle_id) if user.vehicles else None
    label = vehicle.nickname.replace(" ", "-") if vehicle else "vehicle"
    fname = f"cost-entries-{label}-{date.today().isoformat()}.csv"

    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/{entry_id}", response_model=CostEntryOut)
async def get_cost_entry(
    vehicle_id: str,
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CostEntry:
    """Get a single cost entry."""
    await get_accessible_vehicle(db, vehicle_id, user)
    entry = await db.get(CostEntry, entry_id)
    if not entry or entry.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Cost entry not found")
    return entry


@router.patch("/{entry_id}", response_model=CostEntryOut)
async def update_cost_entry(
    vehicle_id: str,
    entry_id: str,
    payload: CostEntryUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> CostEntry:
    """Update a cost entry."""
    await get_accessible_vehicle(db, vehicle_id, user)
    entry = await db.get(CostEntry, entry_id)
    if not entry or entry.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Cost entry not found")

    if payload.receipt_id:
        receipt = await db.get(Receipt, payload.receipt_id)
        if not receipt or receipt.vehicle_id != vehicle_id:
            raise HTTPException(status_code=404, detail="Receipt not found for this vehicle")

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(entry, key, value)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=204)
async def delete_cost_entry(
    vehicle_id: str,
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> None:
    """Delete a cost entry."""
    await get_accessible_vehicle(db, vehicle_id, user)
    entry = await db.get(CostEntry, entry_id)
    if not entry or entry.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Cost entry not found")
    await db.delete(entry)
    await db.commit()