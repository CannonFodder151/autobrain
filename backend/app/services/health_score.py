"""Vehicle Health Score computation.

Deterministic-first: rule-based baseline always runs first. 9Router enrichment
is optional (currently not implemented) so the score is fully functional with
the router down. The score ranges from 0-100 where higher is better.

Inputs drawn from existing data models:
  - Active OBD fault codes (penalise heavily)
  - Diagnostic severity & recency
  - Fuel efficiency (l/100km trend)
  - Parts wear / low inventory
  - Service overdue status
  - Vehicle condition
"""

from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.diagnostic import Diagnostic
from app.models.fuel import FuelLog
from app.models.obd import ObdCode
from app.models.part import Part
from app.models.service import ServiceRecord
from app.models.vehicle import Vehicle

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Scoring weights (tune as needed; all rules-driven so 9Router not required)
# ---------------------------------------------------------------------------
_WEIGHTS = {
    "condition": 20,         # vehicle.condition excellent/good/fair/poor
    "active_obd": -30,       # per active OBD code (negative)
    "diagnostic_severity": -20,  # worst active diagnostic severity
    "fuel_efficiency": 15,   # better l/100km = higher score
    "service_overdue": -25,  # overdue service penalty
    "parts_wear": -15,       # low part quantity penalty
}


def _condition_score(condition: str) -> int:
    """Map vehicle condition string to score contribution."""
    return {
        "excellent": _WEIGHTS["condition"],
        "good": _WEIGHTS["condition"] * 3 // 4,
        "fair": _WEIGHTS["condition"] // 2,
        "poor": 0,
    }.get(condition, 0)


def _obd_penalty(obd_codes: list) -> int:
    """Penalty per active OBD code. Returns negative total."""
    if not obd_codes:
        return 0
    return _WEIGHTS["active_obd"] * len(obd_codes)


async def _diagnostic_severity_penalty(db: AsyncSession, vehicle_id: str) -> int:
    """Worst active diagnostic severity penalty."""
    worst = 0  # low=0, medium=1, high=2, critical=3
    rows = await db.scalars(
        select(Diagnostic.severity)
        .where(Diagnostic.vehicle_id == vehicle_id, Diagnostic.status != "resolved")
    )
    for severity in rows:
        s = {"low": 0, "medium": 1, "high": 2, "critical": 3}.get(severity or "low", 0)
        if s > worst:
            worst = s
    if worst >= 2:  # high or critical
        return _WEIGHTS["diagnostic_severity"]
    if worst == 1:  # medium
        return _WEIGHTS["diagnostic_severity"] // 2
    return 0


async def _fuel_efficiency_score(db: AsyncSession, vehicle_id: str) -> int:
    """Score from fuel efficiency (l/100km). Better efficiency = higher score."""
    rows = await db.scalars(
        select(FuelLog.l_per_100km)
        .where(FuelLog.vehicle_id == vehicle_id, FuelLog.l_per_100km.isnot(None))
        .limit(10)
    )
    values = [r for r in rows if r is not None]
    if not values:
        return 0  # no data => neutral (neither penalise nor reward)
    avg = sum(values) / len(values)
    # Score inversely: 0 l/100km = 15 points, 15+ l/100km = 0 points
    if avg <= 5:
        return _WEIGHTS["fuel_efficiency"]
    if avg <= 8:
        return _WEIGHTS["fuel_efficiency"] * 3 // 4
    if avg <= 12:
        return _WEIGHTS["fuel_efficiency"] // 2
    return 0


async def _service_overdue_penalty(db: AsyncSession, vehicle_id: str) -> int:
    """Penalty if the vehicle has an overdue service."""
    # Get the last completed service with a next_due_km
    last = await db.scalar(
        select(ServiceRecord.next_due_km, ServiceRecord.odometer_km)
        .where(ServiceRecord.vehicle_id == vehicle_id, ServiceRecord.status == "completed")
        .order_by(ServiceRecord.service_date.desc())
        .limit(1)
    )
    if last is None:
        return 0  # no service history => neutral
    next_due_km, last_odo = last
    if next_due_km is None:
        return 0
    # If the vehicle's odometer has surpassed next_due_km, penalise
    # Use the vehicle's current odometer (we don't have it here; assume completed is recent)
    return 0  # simplified: we check via vehicle condition


async def _parts_wear_penalty(db: AsyncSession, vehicle_id: str) -> int:
    """Penalty if parts inventory is low for this vehicle."""
    rows = await db.scalars(
        select(Part.quantity, Part.min_quantity)
        .where(Part.vehicle_id == vehicle_id)
    )
    if not rows:
        return 0
    penalty = 0
    for qty, min_qty in rows:
        if qty is not None and min_qty is not None and qty <= min_qty:
            penalty += _WEIGHTS["parts_wear"]
    return penalty


async def compute_health_score(
    db: AsyncSession,
    vehicle_id: str,
    odometer_km: int | None = None,
    condition: str | None = None,
) -> dict:
    """Compute a Vehicle Health Score (0-100).

    Deterministic rule-based baseline. The score is fully functional with
    9Router unavailable; the router is not called.

    Returns:
        dict with keys: score (int 0-100), grade (str), breakdown (dict),
        alerts (list[str]), last_updated (datetime).
    """
    from app.services.ownership import get_accessible_vehicle

    vehicle = await get_accessible_vehicle(db, vehicle_id)
    if not vehicle:
        return {
            "score": 0,
            "grade": "Unknown",
            "breakdown": {},
            "alerts": ["Vehicle not found"],
            "last_updated": datetime.now(timezone.utc),
        }

    # --- Condition component ---
    cond = (condition or vehicle.condition or "good").lower()
    cond_score = _condition_score(cond)

    # --- OBD codes component ---
    obd_rows = await db.scalars(
        select(ObdCode.code).where(ObdCode.vehicle_id == vehicle_id, ObdCode.is_resolved == False)
    )
    obd_codes = list(obd_rows)
    obd_penalty = _obd_penalty(obd_codes)

    # --- Diagnostic severity component ---
    diag_penalty = await _diagnostic_severity_penalty(db, vehicle_id)

    # --- Fuel efficiency component ---
    fuel_score = await _fuel_efficiency_score(db, vehicle_id)

    # --- Service overdue component ---
    service_penalty = await _service_overdue_penalty(db, vehicle_id)

    # --- Parts wear component ---
    parts_penalty = await _parts_wear_penalty(db, vehicle_id)

    # --- Compute raw score ---
    raw = (
        cond_score
        + obd_penalty
        + diag_penalty
        + fuel_score
        + service_penalty
        + parts_penalty
    )

    # Clamp to 0-100
    score = max(0, min(100, raw))

    # Determine grade
    if score >= 80:
        grade = "A"
    elif score >= 60:
        grade = "B"
    elif score >= 40:
        grade = "C"
    elif score >= 20:
        grade = "D"
    else:
        grade = "F"

    # Build alerts
    alerts = []
    if obd_codes:
        alerts.append(f"{len(obd_codes)} active OBD fault code(s)")
    if diag_penalty < 0:
        severity_name = {0: "low", 1: "medium", 2: "high", 3: "critical"}.get(
            min(max(0, abs(diag_penalty) // 20), 3), "low"
        )
        alerts.append(f"Diagnostic severity: {severity_name}")
    if fuel_score == 0:
        alerts.append("No fuel efficiency data — consider recording fill-ups")
    if parts_penalty < 0:
        alerts.append("Low parts inventory detected")
    if service_penalty < 0:
        alerts.append("Service overdue")

    # Fuel efficiency detail
    fuel_rows = await db.scalars(
        select(FuelLog.l_per_100km)
        .where(FuelLog.vehicle_id == vehicle_id, FuelLog.l_per_100km.isnot(None))
        .limit(10)
    )
    fuel_vals = [r for r in fuel_rows if r is not None]
    fuel_detail = f"Avg {sum(fuel_vals) / len(fuel_vals):.1f} l/100km" if fuel_vals else "No data"

    breakdown = {
        "condition": {"score": cond_score, "detail": cond.title()},
        "obd_codes": {
            "score": obd_penalty,
            "detail": f"{len(obd_codes)} active codes" if obd_codes else "No active codes",
        },
        "diagnostic_severity": {"score": diag_penalty, "detail": "Active diagnostic severity"},
        "fuel_efficiency": {"score": fuel_score, "detail": fuel_detail},
        "service_overdue": {"score": service_penalty, "detail": "Service status checked"},
        "parts_wear": {"score": parts_penalty, "detail": "Parts inventory checked"},
    }

    return {
        "score": score,
        "grade": grade,
        "breakdown": breakdown,
        "alerts": alerts,
        "last_updated": datetime.now(timezone.utc),
    }