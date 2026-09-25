"""Deterministic Vehicle Health Score engine (0-100).

Fuses diagnostics, maintenance history, fuel efficiency, OBD codes, and parts
wear into a single 0-100 score with predictive failure alerts.

Deterministic-first: the rule engine always runs and its score is authoritative.
The AI gateway (health-score module) may only enrich the narrative/summary.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.diagnostic import Diagnostic
from app.models.fuel import FuelLog
from app.models.obd import ObdCode
from app.models.part import Part
from app.models.service import ServiceRecord
from app.models.vehicle import Vehicle
from app.schemas.health_score import (
    HealthScoreResponse,
    PredictiveAlert,
    ScoreBreakdown,
)


# --- Scoring constants ---------------------------------------------------------

# Max points per component (sum = 100)
_MAX_DIAGNOSTICS = 25
_MAX_MAINTENANCE = 25
_MAX_FUEL_EFFICIENCY = 25
_MAX_OBD_CODES = 15
_MAX_PARTS = 10

# Diagnostic severity penalties (per open issue)
_DIAG_PENALTY = {
    "critical": 25,
    "high": 12,
    "medium": 6,
    "low": 2,
}

# OBD code severity (active unresolved codes)
_OBD_PENALTY = {
    "critical": 15,
    "high": 8,
    "medium": 4,
    "low": 2,
}

# Maintenance scoring
_SERVICE_WINDOW_DAYS = 365  # expected annual service
_SERVICE_WINDOW_KM = 15_000  # expected km between services
_SERVICE_GRACE_DAYS = 30
_SERVICE_GRACE_KM = 1_000

# Fuel efficiency: compare recent vs historical average
_FUEL_COMPARISON_WINDOW = 3  # last N fills
_FUEL_EFFICIENCY_TOLERANCE = 0.15  # 15% degradation triggers penalty

# Parts inventory
_PARTS_REORDER_PENALTY = 2  # per part at/below min_quantity

# Labels
_LABEL_THRESHOLDS = {
    "excellent": 90,
    "good": 75,
    "fair": 55,
    "poor": 35,
    "critical": 0,
}


def _label_for_score(score: float) -> str:
    for label, threshold in _LABEL_THRESHOLDS.items():
        if score >= threshold:
            return label
    return "critical"


def _confidence_from_signals(signal_count: int, data_sources: int) -> float:
    """Compute confidence based on available data sources and signal richness."""
    base = 0.5
    source_bonus = min(data_sources * 0.1, 0.3)
    signal_bonus = min(signal_count * 0.02, 0.15)
    return round(min(base + source_bonus + signal_bonus, 0.95), 2)


async def _compute_diagnostics_score(db: AsyncSession, vehicle_id: str) -> tuple[float, list[str], list[PredictiveAlert]]:
    """Diagnostics component: 0-25 points from open diagnostic issues."""
    signals: list[str] = []
    alerts: list[PredictiveAlert] = []

    rows = await db.scalars(
        select(Diagnostic)
        .where(Diagnostic.vehicle_id == vehicle_id, Diagnostic.status == "open")
        .order_by(Diagnostic.created_at.desc())
    )
    open_diags = list(rows)

    if not open_diags:
        return _MAX_DIAGNOSTICS, ["No open diagnostics"], []

    penalty = 0
    for diag in open_diags:
        severity = (diag.severity or "low").lower()
        penalty += _DIAG_PENALTY.get(severity, 2)
        signals.append(f"Open {severity} diagnostic: {diag.summary or diag.symptoms[:80]}")

        alerts.append(PredictiveAlert(
            component="diagnostics",
            alert_type="diagnostic_open",
            severity=severity,
            message=f"Open diagnostic: {diag.summary or diag.symptoms[:80]}",
            source_id=diag.id,
        ))

    score = max(_MAX_DIAGNOSTICS - min(penalty, _MAX_DIAGNOSTICS), 0)
    return round(score, 1), signals, alerts


async def _compute_maintenance_score(
    db: AsyncSession, vehicle_id: str, vehicle: Vehicle
) -> tuple[float, list[str], list[PredictiveAlert]]:
    """Maintenance component: 0-25 points from service history and due status."""
    signals: list[str] = []
    alerts: list[PredictiveAlert] = []

    # Completed services count
    completed = await db.scalars(
        select(ServiceRecord)
        .where(ServiceRecord.vehicle_id == vehicle_id, ServiceRecord.status == "completed")
        .order_by(ServiceRecord.service_date.desc())
    )
    completed_list = list(completed)
    service_count = len(completed_list)

    # Days/km since last service
    last_service = completed_list[0] if completed_list else None
    today = date.today()
    last_days = None
    last_km = None

    if last_service:
        last_days = (today - last_service.service_date).days
        last_km = (vehicle.odometer_km or 0) - last_service.odometer_km

        signals.append(f"Last service: {last_days} days ago, {last_km:,} km ago")

        # Check if overdue by time
        if last_days > _SERVICE_WINDOW_DAYS + _SERVICE_GRACE_DAYS:
            alerts.append(PredictiveAlert(
                component="maintenance",
                alert_type="service_overdue",
                severity="high" if last_days > _SERVICE_WINDOW_DAYS * 2 else "medium",
                message=f"Service overdue by {last_days - _SERVICE_WINDOW_DAYS} days",
                due_in_days=last_days - _SERVICE_WINDOW_DAYS,
                source_id=last_service.id,
            ))

        # Check if overdue by km
        if last_km > _SERVICE_WINDOW_KM + _SERVICE_GRACE_KM:
            alerts.append(PredictiveAlert(
                component="maintenance",
                alert_type="service_overdue",
                severity="high" if last_km > _SERVICE_WINDOW_KM * 2 else "medium",
                message=f"Service overdue by {last_km - _SERVICE_WINDOW_KM:,} km",
                due_in_km=last_km - _SERVICE_WINDOW_KM,
                source_id=last_service.id,
            ))

    # Score based on service coverage
    if service_count == 0:
        score = 0
        signals.append("No service history")
    elif service_count == 1:
        score = _MAX_MAINTENANCE * 0.4
        signals.append("Minimal service history (1 record)")
    elif service_count == 2:
        score = _MAX_MAINTENANCE * 0.7
        signals.append("Limited service history (2 records)")
    else:
        score = _MAX_MAINTENANCE
        signals.append(f"Good service history ({service_count} records)")

    # Penalty for overdue
    if last_days and last_days > _SERVICE_WINDOW_DAYS:
        overdue_factor = min((last_days - _SERVICE_WINDOW_DAYS) / _SERVICE_WINDOW_DAYS, 1.0)
        score *= (1 - 0.5 * overdue_factor)
        signals.append(f"Service overdue by {last_days - _SERVICE_WINDOW_DAYS} days")

    if last_km and last_km > _SERVICE_WINDOW_KM:
        overdue_factor = min((last_km - _SERVICE_WINDOW_KM) / _SERVICE_WINDOW_KM, 1.0)
        score *= (1 - 0.5 * overdue_factor)
        signals.append(f"Service overdue by {last_km - _SERVICE_WINDOW_KM:,} km")

    return round(max(score, 0), 1), signals, alerts


async def _compute_fuel_efficiency_score(
    db: AsyncSession, vehicle_id: str, vehicle: Vehicle
) -> tuple[float, list[str], list[PredictiveAlert]]:
    """Fuel efficiency component: 0-25 points from L/100km trend."""
    signals: list[str] = []
    alerts: list[PredictiveAlert] = []

    rows = await db.scalars(
        select(FuelLog)
        .where(FuelLog.vehicle_id == vehicle_id, FuelLog.is_full_tank == True)
        .order_by(FuelLog.odometer_km.asc())
    )
    full_fills = list(rows)

    if len(full_fills) < 3:
        return _MAX_FUEL_EFFICIENCY * 0.5, ["Insufficient fuel data for efficiency trend"], []

    # Compute historical average (all but last N)
    historical = full_fills[:-_FUEL_COMPARISON_WINDOW]
    recent = full_fills[-_FUEL_COMPARISON_WINDOW:]

    if not historical or not recent:
        return _MAX_FUEL_EFFICIENCY * 0.5, ["Insufficient fuel data split"], []

    hist_eff = [f.l_per_100km for f in historical if f.l_per_100km is not None]
    recent_eff = [f.l_per_100km for f in recent if f.l_per_100km is not None]

    if not hist_eff or not recent_eff:
        return _MAX_FUEL_EFFICIENCY * 0.5, ["No efficiency data available"], []

    avg_hist = sum(hist_eff) / len(hist_eff)
    avg_recent = sum(recent_eff) / len(recent_eff)

    degradation = (avg_recent - avg_hist) / avg_hist if avg_hist > 0 else 0
    signals.append(f"Fuel efficiency: {avg_recent:.1f} vs {avg_hist:.1f} L/100km ({degradation:+.1%})")

    if degradation > _FUEL_EFFICIENCY_TOLERANCE:
        penalty = min(degradation / _FUEL_EFFICIENCY_TOLERANCE, 1.0) * _MAX_FUEL_EFFICIENCY * 0.6
        score = max(_MAX_FUEL_EFFICIENCY - penalty, 0)
        alerts.append(PredictiveAlert(
            component="fuel_efficiency",
            alert_type="efficiency_drop",
            severity="high" if degradation > _FUEL_EFFICIENCY_TOLERANCE * 2 else "medium",
            message=f"Fuel efficiency dropped {degradation:.1%} ({avg_recent:.1f} vs {avg_hist:.1f} L/100km)",
            estimated_cost=None,
        ))
    elif degradation > 0:
        penalty = (degradation / _FUEL_EFFICIENCY_TOLERANCE) * _MAX_FUEL_EFFICIENCY * 0.3
        score = max(_MAX_FUEL_EFFICIENCY - penalty, 0)
    else:
        score = _MAX_FUEL_EFFICIENCY
        if degradation < -0.05:
            signals.append("Fuel efficiency improved")

    return round(max(score, 0), 1), signals, alerts


async def _compute_obd_score(db: AsyncSession, vehicle_id: str) -> tuple[float, list[str], list[PredictiveAlert]]:
    """OBD codes component: 0-15 points from active fault codes."""
    signals: list[str] = []
    alerts: list[PredictiveAlert] = []

    rows = await db.scalars(
        select(ObdCode)
        .where(ObdCode.vehicle_id == vehicle_id, ObdCode.is_resolved == False)
        .order_by(ObdCode.created_at.desc())
    )
    active_codes = list(rows)

    if not active_codes:
        return _MAX_OBD_CODES, ["No active OBD codes"], []

    # Categorise codes by prefix severity
    penalty = 0
    for code in active_codes:
        prefix = code.code[:4].upper() if code.code else ""
        # Heuristic: P0xxx (powertrain) = high, B/C/U = medium, P2/P3 = low
        if prefix.startswith("P0") or prefix.startswith("P1"):
            sev = "high"
            penalty += _OBD_PENALTY["high"]
        elif prefix.startswith("P2") or prefix.startswith("P3"):
            sev = "medium"
            penalty += _OBD_PENALTY["medium"]
        elif prefix.startswith("B") or prefix.startswith("C") or prefix.startswith("U"):
            sev = "medium"
            penalty += _OBD_PENALTY["medium"]
        else:
            sev = "low"
            penalty += _OBD_PENALTY["low"]

        signals.append(f"Active OBD code {code.code}: {code.description or 'no description'}")
        alerts.append(PredictiveAlert(
            component="obd_codes",
            alert_type="obd_active",
            severity=sev,
            message=f"Active OBD code {code.code}: {code.description or 'no description'}",
            source_id=code.id,
        ))

    score = max(_MAX_OBD_CODES - min(penalty, _MAX_OBD_CODES), 0)
    return round(score, 1), signals, alerts


async def _compute_parts_score(db: AsyncSession, vehicle_id: str) -> tuple[float, list[str], list[PredictiveAlert]]:
    """Parts component: 0-10 points from inventory health."""
    signals: list[str] = []
    alerts: list[PredictiveAlert] = []

    rows = await db.scalars(
        select(Part).where(Part.vehicle_id == vehicle_id)
    )
    parts = list(rows)

    if not parts:
        return _MAX_PARTS * 0.5, ["No parts inventory tracked"], []

    total = len(parts)
    low_stock = [p for p in parts if p.quantity <= p.min_quantity]
    reorder_count = len(low_stock)

    signals.append(f"Parts inventory: {total} items, {reorder_count} need reorder")

    if reorder_count > 0:
        penalty = min(reorder_count * _PARTS_REORDER_PENALTY, _MAX_PARTS)
        score = max(_MAX_PARTS - penalty, 0)
        for part in low_stock:
            alerts.append(PredictiveAlert(
                component="parts",
                alert_type="part_reorder",
                severity="medium" if part.quantity == 0 else "low",
                message=f"Reorder needed: {part.name} ({part.quantity}/{part.min_quantity} in stock)",
                estimated_cost=part.unit_cost * max(part.min_quantity * 2 - part.quantity, 1) if part.unit_cost > 0 else None,
                source_id=part.id,
            ))
    else:
        score = _MAX_PARTS

    return round(score, 1), signals, alerts


async def compute_health_score(db: AsyncSession, vehicle_id: str, vehicle: Vehicle) -> HealthScoreResponse:
    """Compute the full Vehicle Health Score (0-100) from all components."""

    # Run all component scorers
    diag_score, diag_signals, diag_alerts = await _compute_diagnostics_score(db, vehicle_id)
    maint_score, maint_signals, maint_alerts = await _compute_maintenance_score(db, vehicle_id, vehicle)
    fuel_score, fuel_signals, fuel_alerts = await _compute_fuel_efficiency_score(db, vehicle_id, vehicle)
    obd_score, obd_signals, obd_alerts = await _compute_obd_score(db, vehicle_id)
    parts_score, parts_signals, parts_alerts = await _compute_parts_score(db, vehicle_id)

    # Aggregate
    total_score = round(diag_score + maint_score + fuel_score + obd_score + parts_score)
    total_score = max(min(total_score, 100), 0)

    all_signals = diag_signals + maint_signals + fuel_signals + obd_signals + parts_signals
    all_alerts = diag_alerts + maint_alerts + fuel_alerts + obd_alerts + parts_alerts

    # Count data sources that contributed
    data_sources = sum([
        bool(diag_signals and diag_signals != ["No open diagnostics"]),
        bool(maint_signals and maint_signals != ["No service history"]),
        bool(fuel_signals and fuel_signals != ["Insufficient fuel data for efficiency trend"]),
        bool(obd_signals and obd_signals != ["No active OBD codes"]),
        bool(parts_signals and parts_signals != ["No parts inventory tracked"]),
    ])

    confidence = _confidence_from_signals(len(all_signals), data_sources)

    breakdown = ScoreBreakdown(
        diagnostics=diag_score,
        maintenance=maint_score,
        fuel_efficiency=fuel_score,
        obd_codes=obd_score,
        parts=parts_score,
    )

    return HealthScoreResponse(
        score=total_score,
        label=_label_for_score(total_score),
        breakdown=breakdown,
        confidence=confidence,
        alerts=all_alerts,
        signals=all_signals,
        model="rule-based",
    )