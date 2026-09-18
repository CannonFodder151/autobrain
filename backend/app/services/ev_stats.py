"""EV/PHEV trip statistics service (AUT-2705).

Deterministic, rule-based computation of EV/ICE distance splits, SOC deltas,
and Wh/km efficiency from logbook entries and dongle telemetry. No AI.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.models.logbook import LogEntry
    from app.models.vehicle import Vehicle


VALID_VEHICLE_TYPES = {"ice", "ev", "hev", "phev"}


def normalize_vehicle_type(raw: str | None) -> str | None:
    """Normalize a vehicle_type string to canonical lowercase enum value."""
    if raw is None:
        return None
    v = raw.strip().lower()
    return v if v in VALID_VEHICLE_TYPES else None


def classify_trip_type(log: "LogEntry", telemetry_ev_mode: int | None = None) -> str:
    """Determine the powertrain mode for a single trip.

    Precedence:
      1. Explicit vehicle_type on the log entry (set by dongle firmware).
      2. Inferred from telemetry ev_mode flag (0=ICE, 1=EV, 2=HYBRID).
      3. Vehicle's registered powertrain as fallback.
    """
    if log.vehicle_type:
        return log.vehicle_type

    if telemetry_ev_mode is not None:
        if telemetry_ev_mode == 1:
            return "ev"
        if telemetry_ev_mode == 2:
            return "hev"
        if telemetry_ev_mode == 3:
            return "phev"
        return "ice"

    return "ice"


def split_distance(
    total_distance_km: float | None,
    vehicle_type: str,
    ev_distance_km: float | None = None,
    ice_distance_km: float | None = None,
) -> tuple[float | None, float | None]:
    """Split a trip's total distance into EV and ICE components.

    If ev_distance_km/ice_distance_km are already provided (dongle-calculated),
    use them. Otherwise, infer from vehicle_type:
      - ev: all EV
      - hev/phev: 50/50 heuristic if no telemetry (conservative)
      - ice: all ICE
    """
    if total_distance_km is None:
        return (None, None)

    if ev_distance_km is not None and ice_distance_km is not None:
        return (ev_distance_km, ice_distance_km)

    vt = (vehicle_type or "ice").lower()
    if vt == "ev":
        return (total_distance_km, 0.0)
    if vt in ("hev", "phev"):
        # Conservative 50/50 split when per-sample telemetry unavailable.
        half = round(total_distance_km / 2, 2)
        return (half, half)
    return (0.0, total_distance_km)


def compute_soc_delta(
    start_soc_pct: float | None,
    end_soc_pct: float | None,
) -> float | None:
    """SOC delta for a trip (end - start). Negative means discharge."""
    if start_soc_pct is None or end_soc_pct is None:
        return None
    return round(end_soc_pct - start_soc_pct, 2)


def estimate_charge_added_kwh(
    soc_delta_pct: float | None,
    battery_capacity_kwh: float | None,
) -> float | None:
    """Estimate kWh added during a charging session from SOC delta.

    Positive soc_delta -> charge added. Requires vehicle battery capacity.
    """
    if soc_delta_pct is None or battery_capacity_kwh is None:
        return None
    if soc_delta_pct <= 0:
        return None
    return round(battery_capacity_kwh * (soc_delta_pct / 100.0), 2)


def compute_efficiency_wh_per_km(
    ev_distance_km: float | None,
    charge_kwh: float | None,
) -> float | None:
    """Compute Wh/km efficiency for EV distance.

    charge_kwh is the energy consumed (discharged) over ev_distance_km.
    Returns Wh/km (positive). If no EV distance or no charge data, returns None.
    """
    if ev_distance_km is None or ev_distance_km <= 0:
        return None
    if charge_kwh is None or charge_kwh <= 0:
        return None
    return round((charge_kwh * 1000.0) / ev_distance_km, 1)


async def get_vehicle_ev_stats(
    db: AsyncSession,
    vehicle_id: str,
) -> dict:
    """Aggregate EV/PHEV statistics for a vehicle from its logbook entries.

    Returns a dict matching the EvTripStats schema shape.
    """
    from app.models.logbook import LogEntry

    # Fetch all completed trips for the vehicle
    rows = list(
        (
            await db.scalars(
                select(LogEntry)
                .where(LogEntry.vehicle_id == vehicle_id)
                .where(LogEntry.status == "completed")
                .where(LogEntry.distance_km.isnot(None))
                .order_by(LogEntry.started_at.asc())
            )
        ).all()
    )

    if not rows:
        return {
            "total_trips": 0,
            "total_distance_km": 0.0,
            "ev_distance_km": 0.0,
            "ice_distance_km": 0.0,
            "ev_ratio": 0.0,
            "total_charge_kwh": 0.0,
            "avg_efficiency_wh_per_km": None,
            "trips": [],
        }

    total_distance = 0.0
    total_ev = 0.0
    total_ice = 0.0
    total_charge = 0.0
    efficiencies: list[float] = []
    trips_out: list[dict] = []

    for log in rows:
        # Normalize vehicle_type for this trip
        vt = normalize_vehicle_type(log.vehicle_type)

        # Split distance
        ev_km, ice_km = split_distance(
            log.distance_km,
            vt or "ice",
            log.ev_distance_km,
            log.ice_distance_km,
        )

        # Charge added this trip (from SOC delta + battery capacity)
        charge_kwh = log.charge_added_kwh

        # Efficiency if we have EV distance and charge data
        eff = compute_efficiency_wh_per_km(ev_km, charge_kwh)
        if eff is not None:
            efficiencies.append(eff)

        total_distance += log.distance_km or 0.0
        total_ev += ev_km or 0.0
        total_ice += ice_km or 0.0
        total_charge += charge_kwh or 0.0

        trips_out.append({
            "id": log.id,
            "started_at": log.started_at.isoformat() if log.started_at else None,
            "distance_km": log.distance_km,
            "vehicle_type": vt,
            "ev_distance_km": ev_km,
            "ice_distance_km": ice_km,
            "charge_added_kwh": charge_kwh,
            "efficiency_wh_per_km": eff,
        })

    ev_ratio = round(total_ev / total_distance, 3) if total_distance > 0 else 0.0
    avg_eff = round(sum(efficiencies) / len(efficiencies), 1) if efficiencies else None

    return {
        "total_trips": len(rows),
        "total_distance_km": round(total_distance, 2),
        "ev_distance_km": round(total_ev, 2),
        "ice_distance_km": round(total_ice, 2),
        "ev_ratio": ev_ratio,
        "total_charge_kwh": round(total_charge, 2),
        "avg_efficiency_wh_per_km": avg_eff,
        "trips": trips_out,
    }


async def recompute_trip_ev_fields(
    db: AsyncSession,
    vehicle_id: str,
) -> int:
    """Backfill ev_distance_km, ice_distance_km for existing trips.

    Uses the vehicle's powertrain and any existing vehicle_type on the log.
    Returns number of rows updated.
    """
    from app.models.logbook import LogEntry
    from app.models.vehicle import Vehicle, PowertrainType

    vehicle = await db.get(Vehicle, vehicle_id)
    if not vehicle:
        return 0

    fallback_type = vehicle.powertrain.lower() if vehicle.powertrain else "ice"

    rows = list(
        (
            await db.scalars(
                select(LogEntry)
                .where(LogEntry.vehicle_id == vehicle_id)
                .where(LogEntry.status == "completed")
                .where(LogEntry.distance_km.isnot(None))
            )
        ).all()
    )

    updated = 0
    for log in rows:
        vt = normalize_vehicle_type(log.vehicle_type) or fallback_type
        ev_km, ice_km = split_distance(log.distance_km, vt)

        if log.ev_distance_km != ev_km or log.ice_distance_km != ice_km:
            log.ev_distance_km = ev_km
            log.ice_distance_km = ice_km
            updated += 1

    if updated:
        await db.commit()
    return updated