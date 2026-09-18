"""Deterministic health-score fallback (rule-based, no AI).

Computes a 0–100 health score from vehicle data:
  - open diagnostics (severity-weighted)
  - open OBD codes (severity-weighted)
  - maintenance recency
  - fuel efficiency trend
  - parts inventory health

All inputs are pre-fetched by the backend service layer; this module
just applies the scoring formula.  9Router may optionally enrich the
result with a narrative summary and failure predictions.
"""

from __future__ import annotations


# ── Constants ──────────────────────────────────────────────────────
BONUS_SCHEDULED = 5.0
BONUS_GOOD_STOCK = 5.0
PENALTY_MAINTENANCE = 15.0
PENALTY_FUEL = 10.0
PENALTY_PARTS = 5.0


def _clamp(n: float, lo: float = 0.0, hi: float = 100.0) -> int:
    return max(lo, min(hi, round(n)))


def _diagnostic_penalty(diagnostics: list[dict]) -> float:
    total = 0.0
    for d in diagnostics:
        sev = (d.get("severity") or "low").lower()
        if sev == "critical":
            total += 2.0
        elif sev == "high":
            total += 1.0
        elif sev == "medium":
            total += 0.5
        else:
            total += 0.25
    return total


def _obd_penalty(obd_codes: list[dict]) -> float:
    total = 0.0
    for c in obd_codes:
        desc = (c.get("description") or "").lower()
        if "critical" in desc:
            total += 2.0
        elif "high" in desc:
            total += 1.0
        else:
            total += 0.5
    return total


def _maintenance_penalty(completed: int, has_scheduled: bool, months_since_last: float) -> float:
    if completed == 0:
        return PENALTY_MAINTENANCE
    if months_since_last > 12:
        return PENALTY_MAINTENANCE
    if has_scheduled:
        return max(0.0, PENALTY_MAINTENANCE - BONUS_SCHEDULED)
    return 0.0


def _fuel_penalty(avg_l_per_100km: float | None) -> float:
    if avg_l_per_100km is None:
        return PENALTY_FUEL
    if avg_l_per_100km <= 8:
        return -BONUS_GOOD_STOCK
    if avg_l_per_100km >= 20:
        return PENALTY_FUEL
    proportion = (avg_l_per_100km - 8) / (20 - 8)
    return -BONUS_GOOD_STOCK + proportion * (PENALTY_FUEL + BONUS_GOOD_STOCK)


def _parts_penalty(parts: list[dict]) -> float:
    total = 0.0
    for p in parts:
        qty = p.get("quantity", 0) or 0
        min_qty = p.get("min_quantity", 0) or 0
        if qty <= 0:
            total -= PENALTY_PARTS
        elif qty <= min_qty:
            total -= PENALTY_PARTS * 0.5
        else:
            total += BONUS_GOOD_STOCK
    return total


def health_score_fallback(payload: dict) -> dict:
    """Deterministic health score computation.

    Expects payload keys (all provided by the backend service layer):
      - diagnostics: list of {severity: str}
      - obd_codes: list of {description: str}
      - completed_services: int
      - has_scheduled: bool
      - months_since_last_service: float
      - avg_fuel_efficiency: float | None  (L/100km)
      - parts: list of {quantity: int, min_quantity: int}
      - vehicle_age_years: float | None

    Returns dict with score, status_label, breakdown, and optional summary.
    """
    diag_pen = _diagnostic_penalty(payload.get("diagnostics") or [])
    obd_pen = _obd_penalty(payload.get("obd_codes") or [])
    maint_pen = _maintenance_penalty(
        payload.get("completed_services") or 0,
        payload.get("has_scheduled") or False,
        payload.get("months_since_last_service") or 0.0,
    )
    fuel_pen = _fuel_penalty(payload.get("avg_fuel_efficiency"))
    parts_pen = _parts_penalty(payload.get("parts") or [])

    score = 100.0 - diag_pen - obd_pen - maint_pen - fuel_pen - parts_pen

    if score >= 80:
        status_label = "healthy"
    elif score >= 50:
        status_label = "at-risk"
    else:
        status_label = "needs-attention"

    breakdown = {
        "diagnostics": round(diag_pen, 1),
        "obd_codes": round(obd_pen, 1),
        "maintenance": round(maint_pen, 1),
        "fuel_efficiency": round(fuel_pen, 1),
        "parts_wear": round(parts_pen, 1),
    }

    # Build predictive failure alerts from the breakdown
    alerts = _build_alerts(payload, breakdown)

    return {
        "score": _clamp(score),
        "status_label": status_label,
        "breakdown": breakdown,
        "alerts": alerts,
        "model": "rule-based-fallback",
    }


def _build_alerts(payload: dict, breakdown: dict) -> list[dict]:
    """Generate predictive failure alerts from breakdown data."""
    alerts = []
    if breakdown.get("obd_codes", 0) > 1:
        alerts.append({
            "category": "obd",
            "severity": "high",
            "message": "Multiple active OBD codes detected. Get a scan before the check-engine light escalates.",
            "confidence": 0.9,
        })
    if breakdown.get("maintenance", 0) >= 10:
        alerts.append({
            "category": "maintenance",
            "severity": "medium",
            "message": "Service is overdue. Delayed maintenance accelerates wear on engine and drivetrain.",
            "confidence": 0.85,
        })
    if breakdown.get("fuel_efficiency", 0) >= 5:
        alerts.append({
            "category": "fuel",
            "severity": "medium",
            "message": "Fuel efficiency has degraded. Check air filter, tyre pressure, and MAF sensor.",
            "confidence": 0.8,
        })
    if breakdown.get("diagnostics", 0) > 2:
        alerts.append({
            "category": "diagnostic",
            "severity": "high",
            "message": "Multiple open diagnostic issues. Prioritise critical-severity items.",
            "confidence": 0.85,
        })
    if breakdown.get("parts_wear", 0) > 2:
        alerts.append({
            "category": "parts",
            "severity": "medium",
            "message": "Parts inventory is running low. Reorder before the next scheduled service.",
            "confidence": 0.8,
        })
    return alerts