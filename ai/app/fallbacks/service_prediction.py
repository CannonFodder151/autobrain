"""Deterministic service-schedule fallback (manufacturer intervals)."""

from __future__ import annotations

from datetime import date, timedelta

# interval_km, interval_months for common service types
_SCHEDULE: dict[str, tuple[int, int]] = {
    "scheduled": (20000, 12),
    "tyre_rotation": (10000, 12),
    "air_filter": (30000, 24),
    "brake_fluid": (50000, 24),
    "coolant": (100000, 48),
    "transmission": (80000, 48),
    "spark_plugs": (60000, 48),
    "timing_belt": (100000, 60),
    "brake_pads": (40000, 36),
    "battery": (60000, 48),
}

# AUT-1275: "Oil Change" was merged into "Scheduled Service". Old records and
# older clients may still send the legacy type; normalise it so prediction is
# consistent with the merged schedule.
_LEGACY_OIL_TYPES = frozenset({"oil", "oil_change"})

# make-specific interval adjustments (multiplier)
_MAKE_MULT: dict[str, float] = {
    "toyota": 0.9, "honda": 0.9, "mazda": 0.95, "ford": 1.0,
    "holden": 1.0, "bmw": 1.1, "audi": 1.1, "mercedes": 1.1,
    "land rover": 1.2, "jaguar": 1.2, "subaru": 0.95,
}


def predict_service_fallback(payload: dict) -> dict:
    make = (payload.get("make") or "").lower()
    service_type = payload.get("service_type", "scheduled")
    if service_type in _LEGACY_OIL_TYPES:
        service_type = "scheduled"
    history = [h for h in (payload.get("service_history") or []) if isinstance(h, dict)]

    interval_km, interval_months = _SCHEDULE.get(service_type, _SCHEDULE["scheduled"])
    interval_km = int(interval_km * _MAKE_MULT.get(make, 1.0))

    odo = int(payload.get("odometer_km") or 0)
    last_km = payload.get("last_service_km")
    last_days = payload.get("last_service_days_ago")

    basis = []
    if history:
        # Prefer services of the same type, else the most recent service overall.
        same = [h for h in history if (h.get("service_type") or "") == service_type]
        refs = same or history
        last = refs[-1]
        last_km = last_km or last.get("odometer_km")
        # Measured interval from consecutive same-type services.
        points = sorted({int(h.get("odometer_km") or 0) for h in same if h.get("odometer_km")})
        if len(points) >= 2:
            gaps = [b - a for a, b in zip(points, points[1:])]
            measured = round(sum(gaps) / len(gaps))
            if measured > 0:
                interval_km = int(measured * _MAKE_MULT.get(make, 1.0))
        if last.get("service_date"):
            try:
                last_days = last_days or max(
                    (date.today() - date.fromisoformat(last["service_date"])).days, 0
                )
            except ValueError:
                pass
        basis.append("history-based")

    if last_days is not None:
        due_date = date.today() + timedelta(days=max(interval_months * 30 - last_days, 0))
        due_in_days = max(interval_months * 30 - last_days, 0)
        basis.append("time-based")
    else:
        due_date = date.today() + timedelta(days=interval_months * 30)
        due_in_days = interval_months * 30
        basis.append("calendar-based")

    next_km = last_km + interval_km if last_km else ((odo // interval_km) + 1) * interval_km
    due_in_km = max(next_km - odo, 0)

    confidence = 0.85 if history else (0.8 if last_km or last_days is not None else 0.6)
    reason = (
        f"Based on {len(history)} past service record(s) ({' + '.join(basis)}), "
        f"{service_type.replace('_', ' ')} on {make or 'this vehicle'} is due every "
        f"~{interval_km:,} km / {interval_months} months. "
        f"Next due at {next_km:,} km (in {due_in_km:,} km) or {due_date.isoformat()}."
    )
    return {
        "service_type": service_type,
        "interval_km": interval_km,
        "interval_months": interval_months,
        "due_in_km": due_in_km,
        "due_in_days": due_in_days,
        "next_due_km": next_km,
        "next_due_date": due_date.isoformat(),
        "confidence": confidence,
        "reason": reason,
        "model": "rule-based-fallback",
    }
