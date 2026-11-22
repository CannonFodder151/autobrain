"""PHEV dual-source tracking service (AUT-734).

Combines ICE fuel logs (fuel_logs) with EV/PHEV trip data (logbook_entries)
into combined efficiency metrics, cost-per-distance, AI usage recommendations,
and CSV export. Deterministic-first: every AI call has a rule-based fallback so
the endpoints always answer even when the 9Router gateway is unreachable.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.fuel import FuelLog
from app.models.logbook import LogEntry
from app.models.vehicle import Vehicle, PowertrainType
from app.schemas.phev import (
    PhevAiInsight,
    PhevCostMetrics,
    PhevDashboardOut,
    PhevDistanceMetrics,
    PhevEnergyMetrics,
    PhevEfficiencyMetrics,
    PhevExportResponse,
    PhevTimelineEventOut,
    PhevTimelineOut,
)
from app.services.ai_client import run_advisor_ai
from app.services.ev_stats import normalize_vehicle_type

logger = get_logger(__name__)

# EPA: 1 US gallon of gasoline contains 33.7 kWh of energy (MPGe basis).
_KWH_PER_GALLON_GASOLINE = 33.7
_LITRES_PER_US_GALLON = 3.78541
_KM_PER_MILE = 1.609344

# Default retail electricity price (AUD/kWh) used when no tariff is on file.
# Overridable per call via ``electricity_price_per_kwh``.
DEFAULT_ELECTRICITY_PRICE_PER_KWH = 0.30


def _compute_mpge(
    distance_km: float, fuel_litres: float, charge_kwh: float
) -> float | None:
    """Combined MPGe: distance in miles / (fuel gallons + kWh/33.7).

    Returns None when there is no distance or no energy consumed at all.
    """
    if distance_km <= 0:
        return None
    fuel_gallons = fuel_litres / _LITRES_PER_US_GALLON
    ev_gallons_eq = charge_kwh / _KWH_PER_GALLON_GASOLINE
    total_gallons_eq = fuel_gallons + ev_gallons_eq
    if total_gallons_eq <= 0:
        return None
    distance_miles = distance_km / _KM_PER_MILE
    return round(distance_miles / total_gallons_eq, 1)


def _combined_l_per_100km_equiv(
    distance_km: float, fuel_litres: float, charge_kwh: float
) -> float | None:
    """Litres-of-gasoline-equivalent per 100 km for the combined drivetrain."""
    if distance_km <= 0:
        return None
    fuel_gallons_eq = charge_kwh / _KWH_PER_GALLON_GASOLINE * _LITRES_PER_US_GALLON
    total_litres_eq = fuel_litres + fuel_gallons_eq
    if total_litres_eq <= 0:
        return None
    return round(total_litres_eq / distance_km * 100, 2)


async def _fetch_fuel_logs(
    db: AsyncSession, vehicle_id: str, start: date | None, end: date | None
) -> list[FuelLog]:
    stmt = (
        select(FuelLog)
        .where(FuelLog.vehicle_id == vehicle_id)
        .order_by(FuelLog.fill_date.asc())
    )
    if start:
        stmt = stmt.where(FuelLog.fill_date >= start)
    if end:
        stmt = stmt.where(FuelLog.fill_date <= end)
    return list((await db.scalars(stmt)).all())


async def _fetch_ev_trips(
    db: AsyncSession, vehicle_id: str, start: date | None, end: date | None
) -> list[LogEntry]:
    stmt = (
        select(LogEntry)
        .where(LogEntry.vehicle_id == vehicle_id)
        .where(LogEntry.status == "completed")
        .where(LogEntry.distance_km.isnot(None))
        .order_by(LogEntry.started_at.asc())
    )
    if start:
        stmt = stmt.where(
            LogEntry.started_at
            >= datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
        )
    if end:
        stmt = stmt.where(
            LogEntry.started_at
            <= datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=timezone.utc)
        )
    return list((await db.scalars(stmt)).all())


async def compute_phev_dashboard(
    db: AsyncSession,
    vehicle_id: str,
    *,
    period_days: int = 365,
    electricity_price_per_kwh: float | None = None,
) -> PhevDashboardOut:
    """Aggregate dual-source (ICE fuel + EV trip) metrics for a vehicle.

    Falls back to zeros when the vehicle has no fuel logs or EV trips.
    """
    vehicle = await db.get(Vehicle, vehicle_id)
    powertrain = vehicle.powertrain if vehicle else PowertrainType.ICE.value

    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=period_days)

    fuel_logs = await _fetch_fuel_logs(db, vehicle_id, start_date, end_date)
    ev_trips = await _fetch_ev_trips(db, vehicle_id, start_date, end_date)

    price = (
        electricity_price_per_kwh
        if electricity_price_per_kwh is not None
        else DEFAULT_ELECTRICITY_PRICE_PER_KWH
    )

    # ---- ICE side: fuel logs ----
    fuel_litres = round(sum(log.litres or 0.0 for log in fuel_logs), 2)
    fuel_cost = round(sum(log.total_cost or 0.0 for log in fuel_logs), 2)
    fuel_distance_km = round(
        sum(log.distance_km or 0.0 for log in fuel_logs if log.distance_km), 2
    )

    # ---- EV side: logbook trips ----
    ev_km = round(sum(trip.ev_distance_km or 0.0 for trip in ev_trips), 2)
    ice_trip_km = round(sum(trip.ice_distance_km or 0.0 for trip in ev_trips), 2)
    charge_kwh = round(sum(trip.charge_added_kwh or 0.0 for trip in ev_trips), 2)

    # ---- Combine ----
    # Fuel logs give tank-to-tank ICE driving; logbook trips give the per-trip
    # EV/ICE split. Treated as complementary sources (a PHEV driver logs either
    # fuel fill-ups or trips, typically not both for the same km).
    ice_km = round(fuel_distance_km + ice_trip_km, 2)
    total_km = round(ev_km + ice_km, 2)
    ev_ratio = round(ev_km / total_km, 3) if total_km > 0 else 0.0

    electricity_cost = round(charge_kwh * price, 2)
    total_cost = round(fuel_cost + electricity_cost, 2)

    # Efficiency
    fuel_l_per_100km = (
        round(fuel_litres / fuel_distance_km * 100, 2) if fuel_distance_km > 0 else None
    )
    ev_kwh_per_100km = (
        round(charge_kwh / ev_km * 100, 2) if ev_km > 0 and charge_kwh > 0 else None
    )
    combined_l_eq = _combined_l_per_100km_equiv(total_km, fuel_litres, charge_kwh)
    combined_mpge = _compute_mpge(total_km, fuel_litres, charge_kwh)

    # Cost
    cost_per_km = round(total_cost / total_km, 4) if total_km > 0 else None
    cost_per_mile = (
        round(cost_per_km * _KM_PER_MILE, 4) if cost_per_km is not None else None
    )

    distance = PhevDistanceMetrics(
        total_km=total_km,
        ev_km=ev_km,
        ice_km=ice_km,
        ev_ratio=ev_ratio,
    )
    energy = PhevEnergyMetrics(
        fuel_litres=fuel_litres,
        fuel_cost=fuel_cost,
        charge_kwh=charge_kwh,
        electricity_cost=electricity_cost,
        total_cost=total_cost,
    )
    efficiency = PhevEfficiencyMetrics(
        fuel_l_per_100km=fuel_l_per_100km,
        ev_kwh_per_100km=ev_kwh_per_100km,
        combined_l_per_100km_equiv=combined_l_eq,
        combined_mpge=combined_mpge,
    )
    cost = PhevCostMetrics(cost_per_km=cost_per_km, cost_per_mile=cost_per_mile)

    insights = await _compute_ai_insights(
        vehicle_id,
        powertrain,
        distance,
        energy,
        efficiency,
        cost,
    )

    return PhevDashboardOut(
        vehicle_id=vehicle_id,
        powertrain=powertrain,
        period_days=period_days,
        sources={"fuel_logs": len(fuel_logs), "ev_trips": len(ev_trips)},
        distance=distance,
        energy=energy,
        efficiency=efficiency,
        cost=cost,
        ai_insights=insights,
    )


async def _compute_ai_insights(
    vehicle_id: str,
    powertrain: str,
    distance: PhevDistanceMetrics,
    energy: PhevEnergyMetrics,
    efficiency: PhevEfficiencyMetrics,
    cost: PhevCostMetrics,
) -> list[PhevAiInsight]:
    """AI recommendations for when to use ICE vs EV, with a deterministic fallback."""
    modules = {
        "vehicle_id": vehicle_id,
        "powertrain": powertrain,
        "total_km": distance.total_km,
        "ev_km": distance.ev_km,
        "ice_km": distance.ice_km,
        "ev_ratio": distance.ev_ratio,
        "fuel_litres": energy.fuel_litres,
        "charge_kwh": energy.charge_kwh,
        "fuel_l_per_100km": efficiency.fuel_l_per_100km,
        "ev_kwh_per_100km": efficiency.ev_kwh_per_100km,
        "combined_mpge": efficiency.combined_mpge,
        "cost_per_km": cost.cost_per_km,
        "question": "Should this PHEV driver use ICE or EV for upcoming trips, and when?",
    }
    result = await run_advisor_ai(vehicle_id, modules)
    if isinstance(result, dict) and result.get("insights"):
        try:
            return [
                PhevAiInsight(
                    type=str(it.get("type", "recommendation")),
                    title=str(it.get("title", "")),
                    detail=str(it.get("detail", "")),
                    priority=str(it.get("priority", "medium")),
                )
                for it in result["insights"]
            ]
        except Exception:
            logger.exception("phev_ai_insights_parse_failed")
    return _deterministic_insights(powertrain, distance, efficiency, cost)


def _deterministic_insights(
    powertrain: str,
    distance: PhevDistanceMetrics,
    efficiency: PhevEfficiencyMetrics,
    cost: PhevCostMetrics,
) -> list[PhevAiInsight]:
    """Rule-based fallback so the dashboard always surfaces guidance."""
    insights: list[PhevAiInsight] = []
    if powertrain != "PHEV":
        insights.append(
            PhevAiInsight(
                type="recommendation",
                title="Not a PHEV",
                detail=f"Vehicle powertrain is {powertrain}; dual-source ICE/EV tracking applies to PHEVs.",
                priority="low",
            )
        )
        return insights
    if distance.total_km <= 0:
        insights.append(
            PhevAiInsight(
                type="recommendation",
                title="Start logging trips",
                detail="No fuel or EV trip data yet. Log a fuel fill-up or complete a trip to unlock PHEV insights.",
                priority="medium",
            )
        )
        return insights
    if distance.ev_ratio >= 0.7:
        insights.append(
            PhevAiInsight(
                type="recommendation",
                title="Lean on EV mode",
                detail=f"{distance.ev_ratio:.0%} of your driving is already electric. Keep using EV for short trips and top up the battery overnight.",
                priority="medium",
            )
        )
    elif distance.ev_ratio <= 0.3 and efficiency.ev_kwh_per_100km is not None:
        insights.append(
            PhevAiInsight(
                type="recommendation",
                title="Use EV more for short runs",
                detail=f"EV efficiency is {efficiency.ev_kwh_per_100km} kWh/100km but only {distance.ev_ratio:.0%} of distance is electric. Use EV mode for trips under ~40 km.",
                priority="medium",
            )
        )
    if cost.cost_per_km is not None and efficiency.ev_kwh_per_100km is not None:
        insights.append(
            PhevAiInsight(
                type="savings",
                title="EV running cost",
                detail=f"Combined cost is {cost.cost_per_km:.4f} AUD/km ({cost.cost_per_mile:.4f} AUD/mile). EV-only trips are cheaper per km once home-charged.",
                priority="low",
            )
        )
    if distance.ice_km > distance.ev_km:
        insights.append(
            PhevAiInsight(
                type="alert",
                title="ICE is doing most of the work",
                detail=f"{distance.ice_km:.0f} km ICE vs {distance.ev_km:.0f} km EV. Shift short commutes to EV to cut fuel spend.",
                priority="high",
            )
        )
    return insights


async def compute_phev_timeline(db: AsyncSession, vehicle_id: str) -> PhevTimelineOut:
    """Unified PHEV usage timeline: fuel fill-ups + completed EV/ICE trips.

    Ordered newest first. Mirrors the vehicle timeline scope but surfaces the
    PHEV-relevant fields (litres, kWh, EV/ICE split) on each event.
    """
    fuel_logs = list(
        (
            await db.scalars(
                select(FuelLog)
                .where(FuelLog.vehicle_id == vehicle_id)
                .order_by(FuelLog.fill_date.desc())
            )
        ).all()
    )
    ev_trips = list(
        (
            await db.scalars(
                select(LogEntry)
                .where(LogEntry.vehicle_id == vehicle_id)
                .where(LogEntry.status == "completed")
                .where(LogEntry.distance_km.isnot(None))
                .order_by(LogEntry.started_at.desc())
            )
        ).all()
    )

    events: list[PhevTimelineEventOut] = []
    for log in fuel_logs:
        events.append(
            PhevTimelineEventOut(
                id=log.id,
                event_type="fuel",
                title=f"Fuel {log.litres:.1f}L @ {log.odometer_km:,} km",
                occurred_on=log.fill_date,
                odometer_km=log.odometer_km,
                amount=log.total_cost,
                source_id=log.id,
                litres=log.litres,
            )
        )
    for trip in ev_trips:
        vt = normalize_vehicle_type(trip.vehicle_type) or "ice"
        label = "EV" if vt == "ev" else ("ICE" if vt == "ice" else vt.upper())
        events.append(
            PhevTimelineEventOut(
                id=trip.id,
                event_type="ev_trip",
                title=f"{label} trip {trip.distance_km:.1f} km",
                occurred_on=trip.started_at.date(),
                odometer_km=trip.end_odometer_km or trip.start_odometer_km,
                amount=None,
                source_id=trip.id,
                ev_distance_km=trip.ev_distance_km,
                ice_distance_km=trip.ice_distance_km,
                charge_kwh=trip.charge_added_kwh,
            )
        )

    events.sort(key=lambda e: e.occurred_on, reverse=True)
    return PhevTimelineOut(vehicle_id=vehicle_id, events=events)


def export_phev_csv(
    vehicle_id: str,
    nickname: str,
    fuel_logs: list[FuelLog],
    ev_trips: list[LogEntry],
) -> bytes:
    """CSV export of the dual-source PHEV dataset (fuel + EV trips)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([f"AutoBrain PHEV Dual-Source Report — {nickname} ({vehicle_id})"])
    writer.writerow(["Generated", datetime.now(timezone.utc).isoformat()])
    writer.writerow([])
    writer.writerow(["--- ICE fuel fill-ups ---"])
    writer.writerow(
        [
            "Date",
            "Odometer (km)",
            "Litres",
            "Price/L",
            "Total cost (AUD)",
            "Full tank",
            "Notes",
        ]
    )
    for log in fuel_logs:
        writer.writerow(
            [
                log.fill_date.isoformat(),
                log.odometer_km,
                log.litres,
                log.price_per_litre,
                log.total_cost,
                "yes" if log.is_full_tank else "no",
                log.notes or "",
            ]
        )
    writer.writerow([])
    writer.writerow(["--- EV / PHEV trips ---"])
    writer.writerow(
        [
            "Date",
            "Distance (km)",
            "EV distance (km)",
            "ICE distance (km)",
            "Charge added (kWh)",
            "Vehicle type",
            "Source",
        ]
    )
    for trip in ev_trips:
        writer.writerow(
            [
                trip.started_at.date().isoformat(),
                trip.distance_km or "",
                trip.ev_distance_km or "",
                trip.ice_distance_km or "",
                trip.charge_added_kwh or "",
                trip.vehicle_type or "ice",
                trip.source or "manual",
            ]
        )
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")


def phev_export_filename(nickname: str, fy: int | None) -> str:
    label = nickname.replace(" ", "-")
    year_tag = f"-FY{fy-1}-{str(fy)[2:]}" if fy else ""
    return f"phev-{label}{year_tag}.csv"


async def build_phev_export(
    db: AsyncSession,
    vehicle_id: str,
    nickname: str,
    *,
    fy: int | None = None,
) -> tuple[PhevExportResponse, bytes]:
    """Assemble the PHEV export payload (metadata + CSV bytes)."""
    end_date = datetime.now(timezone.utc).date()
    if fy:
        start = date(fy - 1, 7, 1)
        end = date(fy, 6, 30)
    else:
        start = date(end_date.year - 1, 7, 1)
        end = end_date
    fuel_logs = await _fetch_fuel_logs(db, vehicle_id, start, end)
    ev_trips = await _fetch_ev_trips(db, vehicle_id, start, end)
    csv_bytes = export_phev_csv(vehicle_id, nickname, fuel_logs, ev_trips)
    return (
        PhevExportResponse(
            filename=phev_export_filename(nickname, fy),
            content_type="text/csv",
            size_bytes=len(csv_bytes),
        ),
        csv_bytes,
    )
