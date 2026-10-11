"""Deterministic Vehicle Health Score fallback.

Score breakdown (total 100):
  - Diagnostics (0-25): based on recent diagnostic severity and resolution status
  - Maintenance (0-25): based on service coverage vs manufacturer intervals
  - Fuel Efficiency (0-25): based on actual vs expected L/100km
  - OBD Codes (0-15): based on active/unresolved fault codes
  - Parts Wear (0-10): based on parts inventory age and replacement history

Label thresholds:
  - 90-100: excellent
  - 75-89: good
  - 60-74: fair
  - 40-59: poor
  - 0-39: critical
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from typing import Any

from .utils import to_float, validate_confidence


# Manufacturer expected fuel economy (L/100km) by vehicle type
_EXPECTED_FUEL_ECONOMY: dict[str, float] = {
    "hatchback": 6.5,
    "sedan": 7.5,
    "suv": 9.5,
    "ute": 11.0,
    "van": 10.5,
    "coupe": 8.5,
    "wagon": 8.0,
    "convertible": 9.0,
    "ev": 0.0,  # handled separately
}

# Service interval baselines (km, months) by service type
_SERVICE_INTERVALS: dict[str, tuple[int, int]] = {
    "scheduled": (15000, 12),
    "oil": (10000, 6),
    "major": (30000, 24),
    "tire": (40000, 24),
    "brake": (50000, 36),
    "transmission": (60000, 48),
    "coolant": (80000, 60),
}

# OBD code severity weights
_OBD_SEVERITY: dict[str, int] = {
    "P0": 3,  # Powertrain - high impact
    "B0": 2,  # Body
    "C0": 2,  # Chassis
    "U0": 1,  # Network
}


def _label_for_score(score: int) -> str:
    if score >= 90:
        return "excellent"
    if score >= 75:
        return "good"
    if score >= 60:
        return "fair"
    if score >= 40:
        return "poor"
    return "critical"


def _diagnostics_score(diagnostics: list[dict]) -> tuple[int, list[str], float]:
    """Score diagnostics 0-25 based on recent severity and resolution."""
    if not diagnostics:
        return 25, ["No recent diagnostics"], 0.9

    now = datetime.now(timezone.utc)
    recent = [d for d in diagnostics if (now - d.get("created_at", now)).days <= 90]
    if not recent:
        return 25, ["No diagnostics in last 90 days"], 0.85

    unresolved = [d for d in recent if d.get("status") != "resolved"]
    high_sev = [d for d in unresolved if d.get("severity") in ("high", "critical")]
    med_sev = [d for d in unresolved if d.get("severity") == "medium"]

    score = 25
    reasons = []
    if high_sev:
        score -= min(len(high_sev) * 8, 20)
        reasons.append(f"{len(high_sev)} high/critical unresolved")
    if med_sev:
        score -= min(len(med_sev) * 4, 12)
        reasons.append(f"{len(med_sev)} medium unresolved")
    score = max(0, score)
    confidence = 0.9 - (0.1 * min(len(unresolved), 3))
    return score, reasons or ["All recent diagnostics resolved"], confidence


def _maintenance_score(
    services: list[dict], vehicle: dict, odometer_km: int
) -> tuple[int, list[str], float]:
    """Score maintenance 0-25 based on service coverage vs intervals."""
    if not services:
        return 0, ["No service history"], 0.5

    completed = [s for s in services if s.get("status") == "completed"]
    if not completed:
        return 5, ["Only scheduled services, none completed"], 0.6

    # Check coverage of key service types
    service_types = {s.get("service_type") for s in completed}
    required = {"scheduled", "oil"}
    missing = required - service_types

    # Check recency of scheduled service
    scheduled = [s for s in completed if s.get("service_type") == "scheduled"]
    last_scheduled = max(scheduled, key=lambda s: s.get("service_date", date.min)) if scheduled else None
    recency_penalty = 0
    if last_scheduled:
        days_since = (date.today() - last_scheduled["service_date"]).days
        km_since = odometer_km - (last_scheduled.get("odometer_km") or 0)
        if days_since > 365 or km_since > 15000:
            recency_penalty = min(10, max(days_since // 36, km_since // 1500))

    score = 25 - (len(missing) * 8) - recency_penalty
    reasons = []
    if missing:
        reasons.append(f"Missing: {', '.join(missing)}")
    if recency_penalty:
        reasons.append(f"Last scheduled service {days_since}d / {km_since}km ago")
    score = max(0, score)
    confidence = 0.8 - (0.1 * len(missing))
    return score, reasons or ["Service coverage adequate"], confidence


def _fuel_score(fuel_logs: list[dict], vehicle: dict) -> tuple[int, list[str], float]:
    """Score fuel efficiency 0-25 based on actual vs expected L/100km."""
    vtype = (vehicle.get("vehicle_type") or "sedan").lower()
    expected = _EXPECTED_FUEL_ECONOMY.get(vtype, 8.0)

    if expected == 0:  # EV
        return 25, ["EV - no fuel consumption"], 0.95

    valid = [f for f in fuel_logs if f.get("l_per_100km") and f.get("is_full_tank")]
    if len(valid) < 3:
        return 12, ["Insufficient fuel data (<3 full-tank logs)"], 0.4

    avg_l100 = sum(f["l_per_100km"] for f in valid) / len(valid)

    ratio = avg_l100 / expected
    if ratio <= 0.9:
        score = 25
    elif ratio <= 1.0:
        score = 22
    elif ratio <= 1.15:
        score = 18
    elif ratio <= 1.3:
        score = 12
    elif ratio <= 1.5:
        score = 6
    else:
        score = 2

    reasons = [f"Avg {avg_l100:.1f} L/100km vs expected {expected:.1f} ({ratio:.0%})"]
    confidence = min(0.9, 0.5 + (len(valid) / 20))
    return score, reasons, confidence


def _obd_score(obd_codes: list[dict]) -> tuple[int, list[str], float]:
    """Score OBD codes 0-15 based on active fault codes."""
    if not obd_codes:
        return 15, ["No OBD codes recorded"], 0.9

    active = [c for c in obd_codes if not c.get("is_resolved")]
    if not active:
        return 15, ["All OBD codes resolved"], 0.85

    penalty = 0
    reasons = []
    for code_obj in active:
        code = str(code_obj.get("code", "")).upper()
        prefix = code[:2]
        penalty += _OBD_SEVERITY.get(prefix, 2)
        reasons.append(f"Active {code}")

    penalty = min(penalty, 15)
    score = max(0, 15 - penalty)
    confidence = 0.85
    return score, reasons, confidence


def _parts_score(parts: list[dict], services: list[dict]) -> tuple[int, list[str], float]:
    """Score parts wear 0-10 based on inventory age and replacement history."""
    if not parts:
        return 5, ["No parts inventory data"], 0.5

    now = datetime.now(timezone.utc)
    low_stock = [p for p in parts if p.get("quantity", 0) <= p.get("min_quantity", 0)]
    aged = []
    for p in parts:
        warranty = p.get("warranty_months")
        if warranty:
            created = p.get("created_at")
            if isinstance(created, str):
                created = datetime.fromisoformat(created.replace("Z", "+00:00"))
            if created and (now - created).days > warranty * 30:
                aged.append(p.get("name"))

    score = 10
    reasons = []
    if low_stock:
        score -= min(len(low_stock) * 2, 6)
        reasons.append(f"{len(low_stock)} parts at/below min stock")
    if aged:
        score -= min(len(aged) * 1, 4)
        reasons.append(f"{len(aged)} parts past warranty age")
    score = max(0, score)
    confidence = 0.7
    return score, reasons or ["Parts inventory healthy"], confidence


def _predictive_alerts(
    diagnostics: list[dict],
    services: list[dict],
    fuel_logs: list[dict],
    obd_codes: list[dict],
    parts: list[dict],
    vehicle: dict,
    odometer_km: int,
) -> list[dict]:
    """Generate predictive failure alerts."""
    alerts = []
    now = datetime.now(timezone.utc)

    # Upcoming service alerts
    completed = [s for s in services if s.get("status") == "completed"]
    for stype, (int_km, int_months) in _SERVICE_INTERVALS.items():
        stype_services = [s for s in completed if s.get("service_type") == stype]
        if not stype_services:
            if stype in ("scheduled", "oil"):
                alerts.append({
                    "component": stype.replace("_", " ").title(),
                    "severity": "medium" if stype == "scheduled" else "high",
                    "message": f"No {stype} service recorded — due now",
                    "due_km": odometer_km,
                    "due_date": date.today().isoformat(),
                    "confidence": 0.7,
                })
            continue
        last = max(stype_services, key=lambda s: s.get("service_date", date.min))
        last_date = last.get("service_date")
        last_km = last.get("odometer_km") or 0
        if last_date:
            days_since = (date.today() - last_date).days
            km_since = odometer_km - last_km
            if days_since >= int_months * 30 * 0.9 or km_since >= int_km * 0.9:
                severity = "high" if days_since >= int_months * 30 or km_since >= int_km else "medium"
                alerts.append({
                    "component": stype.replace("_", " ").title(),
                    "severity": severity,
                    "message": f"{stype.replace('_', ' ').title()} service due ({days_since}d / {km_since}km since last)",
                    "due_km": last_km + int_km,
                    "due_date": (last_date + timedelta(days=int_months * 30)).isoformat(),
                    "confidence": 0.8,
                })

    # Active OBD alerts
    active_obd = [c for c in obd_codes if not c.get("is_resolved")]
    for c in active_obd[:3]:
        alerts.append({
            "component": "OBD System",
            "severity": "high",
            "message": f"Active fault code {c.get('code')}: {c.get('description') or 'unknown'}",
            "due_km": odometer_km,
            "due_date": date.today().isoformat(),
            "confidence": 0.85,
        })

    # Parts wear alerts
    low_stock = [p for p in parts if p.get("quantity", 0) <= p.get("min_quantity", 0)]
    for p in low_stock[:3]:
        alerts.append({
            "component": "Parts Inventory",
            "severity": "medium",
            "message": f"{p.get('name')} at/below minimum stock ({p.get('quantity')}/{p.get('min_quantity')})",
            "due_km": odometer_km,
            "due_date": date.today().isoformat(),
            "confidence": 0.75,
        })

    # Diagnostics trend
    unresolved_high = [d for d in diagnostics if d.get("status") != "resolved" and d.get("severity") in ("high", "critical")]
    if unresolved_high:
        alerts.append({
            "component": "Diagnostics",
            "severity": "high",
            "message": f"{len(unresolved_high)} unresolved high/critical diagnostic(s)",
            "due_km": odometer_km,
            "due_date": date.today().isoformat(),
            "confidence": 0.9,
        })

    return alerts[:10]  # cap at 10


def health_score_fallback(
    vehicle: dict,
    diagnostics: list[dict],
    services: list[dict],
    fuel_logs: list[dict],
    obd_codes: list[dict],
    parts: list[dict],
) -> dict:
    """Compute deterministic Vehicle Health Score (0-100)."""
    odometer_km = vehicle.get("odometer_km") or 0

    diag_score, diag_reasons, diag_conf = _diagnostics_score(diagnostics)
    maint_score, maint_reasons, maint_conf = _maintenance_score(services, vehicle, odometer_km)
    fuel_score_val, fuel_reasons, fuel_conf = _fuel_score(fuel_logs, vehicle)
    obd_score_val, obd_reasons, obd_conf = _obd_score(obd_codes)
    parts_score_val, parts_reasons, parts_conf = _parts_score(parts, services)

    total = diag_score + maint_score + fuel_score_val + obd_score_val + parts_score_val
    total = max(0, min(100, total))

    breakdown = {
        "diagnostics": {"score": diag_score, "max": 25, "reasons": diag_reasons},
        "maintenance": {"score": maint_score, "max": 25, "reasons": maint_reasons},
        "fuel_efficiency": {"score": fuel_score_val, "max": 25, "reasons": fuel_reasons},
        "obd_codes": {"score": obd_score_val, "max": 15, "reasons": obd_reasons},
        "parts_wear": {"score": parts_score_val, "max": 10, "reasons": parts_reasons},
    }

    # Overall confidence: weighted average
    conf = (
        diag_conf * 0.25
        + maint_conf * 0.25
        + fuel_conf * 0.25
        + obd_conf * 0.15
        + parts_conf * 0.10
    )
    conf = validate_confidence(conf, 0.5)

    alerts = _predictive_alerts(
        diagnostics, services, fuel_logs, obd_codes, parts, vehicle, odometer_km
    )

    signals = []
    if diag_score < 15:
        signals.append("diagnostics_degraded")
    if maint_score < 15:
        signals.append("maintenance_overdue")
    if fuel_score_val < 15:
        signals.append("fuel_efficiency_poor")
    if obd_score_val < 10:
        signals.append("active_obd_codes")
    if parts_score_val < 8:
        signals.append("parts_wear_concern")

    return {
        "score": total,
        "label": _label_for_score(total),
        "confidence": round(conf, 2),
        "breakdown": breakdown,
        "alerts": alerts,
        "signals": signals,
        "model": "rule-based-fallback",
        "computed_at": datetime.now().isoformat(),
    }