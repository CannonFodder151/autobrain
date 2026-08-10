"""Analytics routes: spend, TCO, cost per km, forecasts, insights."""

from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.v1.ownership import get_accessible_vehicle
from app.db.session import get_db
from app.models.fuel import FuelLog
from app.models.mod import Modification
from app.models.service import ServiceRecord
from app.models.user import User
from app.schemas.analytics import AnalyticsResponse, CostForecast, MonthlySpend, SpendSummary

router = APIRouter(prefix="/vehicles/{vehicle_id}/analytics", tags=["analytics"])


@router.get("", response_model=AnalyticsResponse)
async def analytics(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AnalyticsResponse:
    await get_accessible_vehicle(db, vehicle_id, user)

    fuel = list((await db.scalars(
        select(FuelLog).where(FuelLog.vehicle_id == vehicle_id).order_by(FuelLog.fill_date)
    )).all())
    services = list((await db.scalars(
        # Only completed services count towards spend / TCO / cost-per-km.
        select(ServiceRecord).where(
            ServiceRecord.vehicle_id == vehicle_id,
            ServiceRecord.status == "completed",
        )
    )).all())
    scheduled = list((await db.scalars(
        select(ServiceRecord).where(
            ServiceRecord.vehicle_id == vehicle_id,
            ServiceRecord.status == "scheduled",
        ).order_by(ServiceRecord.service_date)
    )).all())
    mods = list((await db.scalars(
        select(Modification).where(Modification.vehicle_id == vehicle_id)
    )).all())

    fuel_total = sum(f.total_cost for f in fuel)
    service_total = sum(s.cost for s in services)
    mod_total = sum(m.cost for m in mods)
    tco = fuel_total + service_total + mod_total

    total_km = 0.0
    if len(fuel) >= 2:
        total_km = max(fuel[-1].odometer_km - fuel[0].odometer_km, 0)

    monthly: dict[str, dict] = defaultdict(lambda: {"fuel": 0.0, "service": 0.0, "mod": 0.0})
    for f in fuel:
        monthly[f.fill_date.strftime("%Y-%m")]["fuel"] += f.total_cost
    for s in services:
        monthly[s.service_date.strftime("%Y-%m")]["service"] += s.cost
    for m in mods:
        if m.install_date:
            monthly[m.install_date.strftime("%Y-%m")]["mod"] += m.cost

    monthly_list = [
        MonthlySpend(month=k, **v) for k, v in sorted(monthly.items())
    ]

    # Simple forecast: average monthly spend over tracked months x 12
    n_months = max(len(monthly), 1)
    avg_monthly = (fuel_total + service_total + mod_total) / n_months
    forecast = CostForecast(
        next_12_months=round(avg_monthly * 12, 2),
        predicted_services=_predicted_services(scheduled),
        confidence=0.7,
        basis=f"Average of {n_months} tracked month(s)",
    )

    insights = _insights(fuel, services, mods, tco, total_km)

    return AnalyticsResponse(
        summary=SpendSummary(
            fuel_total=round(fuel_total, 2),
            service_total=round(service_total, 2),
            mod_total=round(mod_total, 2),
            parts_total=round(sum(s.cost for s in services) * 0.4, 2),
            total_cost_of_ownership=round(tco, 2),
            cost_per_km=round(tco / total_km, 4) if total_km > 0 else None,
            total_km_tracked=round(total_km, 1),
            count_fuel=len(fuel),
            count_services=len(services),
            count_mods=len(mods),
        ),
        monthly=monthly_list,
        forecast=forecast,
        insights=insights,
    )


def _predicted_services(scheduled: list) -> list[dict]:
    out = []
    for s in scheduled:
        out.append({
            "service_type": s.service_type,
            "scheduled_date": str(s.service_date),
            "odometer_km": s.odometer_km,
            "estimated_cost": s.cost,
            "status": s.status,
        })
    return out


def _insights(fuel, services, mods, tco, total_km) -> list[str]:
    out = []
    if fuel:
        eff = [f.l_per_100km for f in fuel if f.l_per_100km]
        if eff:
            avg = sum(eff) / len(eff)
            recent = eff[-3:]
            if recent and sum(recent) / len(recent) > avg * 1.05:
                out.append("Fuel efficiency has dropped recently — check tyre pressure and filters.")
            elif recent and sum(recent) / len(recent) < avg * 0.95:
                out.append("Fuel efficiency is improving. Keep doing what you're doing.")
    if services:
        last = max(services, key=lambda s: s.service_date)
        if last.next_due_km and fuel:
            latest_odo = fuel[-1].odometer_km
            remaining = last.next_due_km - latest_odo
            if remaining < 2000:
                out.append(f"{last.service_type.title()} service due within ~{max(remaining, 0):,} km.")
    if mods and (mod_total := sum(m.cost for m in mods)):
        out.append(f"Modifications total {mod_total:,.0f} — review which add resale value.")
    if total_km > 0:
        out.append(f"Running costs are {tco / total_km:.2f}/km across {total_km:,.0f} km tracked.")
    if not out:
        out.append("Add fuel and service records to unlock AI insights.")
    return out
