"""Deterministic vehicle-condition estimator.

Condition is inferred from *data the app already holds* — diagnostics and
service history — instead of being a user-guessed label or an AI guess:

- open/unresolved diagnostics: severity-weighted penalty (critical/high
  issues mean a mechanically compromised vehicle).
- service history: coverage (count), spend, and how long since the last
  service.
- odometer vs expected kilometres for the vehicle's age (expected km/yr
  differs for cars vs motorcycles).
- modification profile: hard-use mods (performance/engine) hint at harder
  life, cosmetic/audio mods are neutral.

The label (excellent/good/fair/poor) is a pure rule-engine output; the AI
module (app/modules/condition.py) may only add a narrative summary on top.

Input payload keys (all optional):
    vehicle:      {odometer_km, year, vehicle_type}
    diagnostics:  [{"severity": low|medium|high|critical, "status": open|resolved}]
    service_count, total_service_cost, last_service_days_ago
    mods:         [{"category": ...}]
"""

from datetime import date

_CAR_KM_PER_YEAR = 15_000.0
_BIKE_KM_PER_YEAR = 6_000.0
_DIAG_PENALTY = {"critical": 35, "high": 15, "medium": 8, "low": 3}
_EXPECTED_KM_YEAR_MIN = 2_000.0


def estimate_condition(payload: dict) -> dict:
    vehicle = payload.get("vehicle") if isinstance(payload.get("vehicle"), dict) else {}
    vehicle_type = str(vehicle.get("vehicle_type") or "car").lower()
    km_per_year = _BIKE_KM_PER_YEAR if vehicle_type in ("motorcycle", "bike", "motorbike") else _CAR_KM_PER_YEAR

    score = 100.0
    signals: list[str] = []

    # --- diagnostics (open/unresolved issues hurt condition) ---
    diags = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), list) else []
    open_issues = [d for d in diags if isinstance(d, dict) and str(d.get("status") or "open").lower() != "resolved"]
    if open_issues:
        penalty = sum(_DIAG_PENALTY.get(str(d.get("severity") or "low").lower(), 3) for d in open_issues)
        score -= min(penalty, 50)
        signals.append(f"{len(open_issues)} open issue(s)")
        critical = [d for d in open_issues if str(d.get("severity") or "").lower() == "critical"]
        if critical:
            signals.append("critical fault present")
    elif diags:
        signals.append("no open issues")

    # --- service history ---
    service_count = int(payload.get("service_count") or 0)
    if service_count == 0:
        score -= 15
        signals.append("no service history")
    elif service_count < 3:
        score -= 5
        signals.append("sparse service history")
    else:
        score += 2
        signals.append(f"{service_count} services on record")

    if float(payload.get("total_service_cost") or 0) > 0:
        score += 2

    last_days = payload.get("last_service_days_ago")
    if last_days is None:
        score -= 4
        signals.append("no recent service")
    else:
        last_days = float(last_days)
        if last_days > 730:
            score -= 8
            signals.append("service overdue")
        elif last_days > 365:
            score -= 4
        else:
            score += 2
            signals.append("recently serviced")

    # --- odometer vs expected for age ---
    odo = float(vehicle.get("odometer_km") or 0)
    year = int(vehicle.get("year") or date.today().year)
    age = max(date.today().year - year, 0)
    expected_km = max(age * km_per_year, _EXPECTED_KM_YEAR_MIN)
    km_ratio = odo / expected_km if expected_km else 0.0
    if km_ratio > 1.5:
        score -= 10
        signals.append("high kilometres vs age")
    elif km_ratio > 1.1:
        score -= 5

    # --- mods: hard-use profile ---
    mods = payload.get("mods") if isinstance(payload.get("mods"), list) else []
    hard_use = [m for m in mods if isinstance(m, dict) and str(m.get("category") or "").lower()
                in ("performance", "engine", "exhaust", "suspension")]
    if hard_use:
        score -= min(3 * len(hard_use), 12)
        signals.append("modified for performance")

    score = round(max(min(score, 100.0), 0.0), 1)
    condition = "excellent" if score >= 88 else "good" if score >= 72 else "fair" if score >= 52 else "poor"

    evidence_sources = sum([bool(diags), bool(service_count), bool(mods), bool(odo)])
    confidence = round(min(0.5 + 0.12 * evidence_sources, 0.95), 2)

    return {
        "condition": condition,
        "score": score,
        "confidence": confidence,
        "factors": {
            "open_issues": len(open_issues),
            "service_count": service_count,
            "last_service_days_ago": round(last_days, 0) if last_days is not None else None,
            "km_ratio": round(km_ratio, 2),
            "signals": signals,
        },
    }
