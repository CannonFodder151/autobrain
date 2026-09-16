"""Deterministic vehicle health score calculator.

Rule-based first, AI fallback. No 9Router dependency for baseline.

Scoring weights:
  - Diagnostics:     open issues severity-weighted (max ~20 pts penalty)
  - OBD codes:       open fault codes severity-weighted (max ~15 pts penalty)
  - Maintenance:     stale / missing service history (~15 pts penalty)
  - Fuel efficiency: poor / good consumption trend (~10 pts penalty/bonus)
  - Parts wear:      low stock / out of stock (~5 pts penalty/bonus)

Final score is clamped to 0–100.
"""

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.diagnostic import Diagnostic
from app.models.obd import ObdCode
from app.models.fuel import FuelLog
from app.models.service import ServiceRecord
from app.models.part import Part

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.models.vehicle import Vehicle


# ── Scoring constants ──────────────────────────────────────────────
BONUS_GOOD_STOCK = 5.0
BONUS_SCHEDULED = 5.0
PENALTY_MAINTENANCE = 15.0
PENALTY_FUEL = 10.0
PENALTY_PARTS = 5.0


def _clamp(n: float, lo: float = 0.0, hi: float = 100.0) -> int:
    return max(lo, min(hi, round(n)))


def _diagnostic_penalty(diagnostics) -> float:
    if not diagnostics:
        return 0.0
    total = 0.0
    for d in diagnostics:
        sev = (d.severity or "low").lower()
        if sev == "critical":
            total += 2.0
        elif sev == "high":
            total += 1.0
        elif sev == "medium":
            total += 0.5
        else:
            total += 0.25
    return total


def _obd_penalty(obd_codes) -> float:
    if not obd_codes:
        return 0.0
    total = 0.0
    for c in obd_codes:
        desc = (c.description or "").lower()
        if "critical" in desc:
            total += 2.0
        elif "high" in desc:
            total += 1.0
        else:
            total += 0.5
    return total


def _maintenance_penalty(service_records, scheduled_records) -> float:
    if not service_records:
        return PENALTY_MAINTENANCE

    completed = [s for s in service_records if s.status == "completed"]
    if not completed:
        return PENALTY_MAINTENANCE * 0.5

    last_service = max(completed, key=lambda s: s.service_date)
    today = date.today()
    months_since = (today - last_service.service_date).days / 30.0

    if months_since > 12:
        return PENALTY_MAINTENANCE

    if scheduled_records:
        return max(0.0, PENALTY_MAINTENANCE - BONUS_SCHEDULED)
    return 0.0


def _fuel_penalty(fuel_logs) -> float:
    if not fuel_logs:
        return PENALTY_FUEL

    effs = [f.l_per_100km for f in fuel_logs if f.l_per_100km is not None]
    if not effs:
        return PENALTY_FUEL

    avg = sum(effs) / len(effs)
    if avg <= 8:
        return -BONUS_GOOD_STOCK
    if avg >= 20:
        return PENALTY_FUEL
    proportion = (avg - 8) / (20 - 8)
    return -BONUS_GOOD_STOCK + proportion * (PENALTY_FUEL + BONUS_GOOD_STOCK)


def _parts_penalty(parts) -> float:
    if not parts:
        return 0.0
    total = 0.0
    for p in parts:
        qty = p.quantity or 0
        min_qty = p.min_quantity or 0
        if qty <= 0:
            total -= PENALTY_PARTS
        elif qty <= min_qty:
            total -= PENALTY_PARTS * 0.5
        else:
            total += BONUS_GOOD_STOCK
    return total


async def compute_health_score(db: "AsyncSession", vehicle: "Vehicle") -> dict:
    """Compute a deterministic health score (0–100) for a vehicle.

    Returns a dict suitable for the VehicleHealthScoreOut schema.
    """
    vid = vehicle.id

    diagnostics = list((await db.scalars(
        select(Diagnostic).where(
            Diagnostic.vehicle_id == vid, Diagnostic.status == "open"
        )
    )).all())

    obd_codes = list((await db.scalars(
        select(ObdCode).where(
            ObdCode.vehicle_id == vid, ObdCode.is_resolved == False
        )
    )).all())

    fuel_logs = list((await db.scalars(
        select(FuelLog).where(FuelLog.vehicle_id == vid).order_by(FuelLog.fill_date)
    )).all())

    service_records = list((await db.scalars(
        select(ServiceRecord).where(
            ServiceRecord.vehicle_id == vid, ServiceRecord.status == "completed"
        )
    )).all())

    scheduled_records = list((await db.scalars(
        select(ServiceRecord).where(
            ServiceRecord.vehicle_id == vid, ServiceRecord.status == "scheduled"
        )
    )).all())

    parts = list((await db.scalars(
        select(Part).where(Part.vehicle_id == vid)
    )).all())

    diag_pen = _diagnostic_penalty(diagnostics)
    obd_pen = _obd_penalty(obd_codes)
    maint_pen = _maintenance_penalty(service_records, scheduled_records)
    fuel_pen = _fuel_penalty(fuel_logs)
    parts_pen = _parts_penalty(parts)

    score = 100.0 - diag_pen - obd_pen - maint_pen - fuel_pen - parts_pen

    if score >= 80:
        status_label = "healthy"
    elif score >= 50:
        status_label = "at-risk"
    else:
        status_label = "needs-attention"

    return {
        "vehicle_id": vid,
        "nickname": vehicle.nickname,
        "score": _clamp(score),
        "status_label": status_label,
        "breakdown": {
            "diagnostics": round(diag_pen, 1),
            "obd_codes": round(obd_pen, 1),
            "maintenance": round(maint_pen, 1),
            "fuel_efficiency": round(fuel_pen, 1),
            "parts_wear": round(parts_pen, 1),
        },
        "last_computed": datetime.utcnow().isoformat(),
        "computed_by": "deterministic",
    }