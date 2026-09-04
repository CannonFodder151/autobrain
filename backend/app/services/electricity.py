"""Electricity business logic: efficiency chaining + stats aggregation.

Extracted from the router so the rules are unit-testable. Mirrors the
fuel service shape exactly (chain full charges -> distance_km, km/kWh,
cost/km) so an EV owner gets the same UX as an ICE owner.
"""

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.electricity import ElectricityLog
from app.models.receipt import Receipt
from app.schemas.electricity import ElectricityLogOut, ElectricityStats


def ref_time(log: ElectricityLog) -> datetime:
    return datetime.combine(log.charge_date, datetime.min.time())


async def link_receipt(db: AsyncSession, vehicle_id: str, receipt_id: str | None) -> str | None:
    if not receipt_id:
        return None
    r = await db.get(Receipt, receipt_id)
    if not r or r.vehicle_id != vehicle_id:
        raise HTTPException(status_code=404, detail="Receipt not found for this vehicle")
    return receipt_id


async def recompute_efficiency(db: AsyncSession, vehicle_id: str) -> None:
    """Chain full charges into distance / km-per-kWh / cost-per-km.

    Same rules as fuel: only consecutive full charges yield an efficiency.
    Out-of-order odometer rows stay unchained (NULL) so they never poison
    later averages.
    """
    rows = await db.scalars(
        select(ElectricityLog)
        .where(ElectricityLog.vehicle_id == vehicle_id)
        .order_by(ElectricityLog.odometer_km, ElectricityLog.charge_date)
    )
    prev: ElectricityLog | None = None
    for log in rows:
        log.distance_km = None
        log.km_per_kwh = None
        log.cost_per_km = None
        if log.is_full_charge and prev and prev.is_full_charge:
            distance = log.odometer_km - prev.odometer_km
            if distance > 0:
                log.distance_km = distance
                log.km_per_kwh = round(distance / log.kwh, 2)
                log.cost_per_km = round(log.total_cost / distance, 4)
        if log.is_full_charge:
            prev = log


async def compute_electricity_stats(db: AsyncSession, vehicle_id: str) -> ElectricityStats:
    rows = list(
        (
            await db.scalars(
                select(ElectricityLog)
                .where(ElectricityLog.vehicle_id == vehicle_id)
                .order_by(ElectricityLog.charge_date.asc())
            )
        ).all()
    )
    totals = await db.execute(
        select(
            func.coalesce(func.sum(ElectricityLog.kwh), 0),
            func.coalesce(func.sum(ElectricityLog.total_cost), 0),
        ).where(ElectricityLog.vehicle_id == vehicle_id)
    )
    total_kwh, total_cost = totals.one()
    eff = [r for r in rows if r.km_per_kwh is not None]
    costk = [r for r in rows if r.cost_per_km is not None]
    series = [
        {
            "date": str(r.charge_date),
            "odometer": r.odometer_km,
            "km_per_kwh": r.km_per_kwh,
            "cost_per_km": r.cost_per_km,
            "price_per_kwh": r.price_per_kwh,
        }
        for r in rows
    ]
    last = rows[-1] if rows else None
    avg_kwh = round(sum(r.kwh for r in rows) / len(rows), 2) if rows else None
    return ElectricityStats(
        total_kwh=round(total_kwh, 2),
        total_cost=round(total_cost, 2),
        avg_km_per_kwh=round(sum(x.km_per_kwh for x in eff) / len(eff), 2) if eff else None,
        avg_cost_per_km=round(sum(x.cost_per_km for x in costk) / len(costk), 4) if costk else None,
        avg_kwh_per_charge=avg_kwh,
        last_log=ElectricityLogOut.model_validate(last) if last else None,
        series=series,
    )
