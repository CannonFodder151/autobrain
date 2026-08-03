"""Deterministic rule-based engines.

These run whenever the 9Router is unreachable, keeping AutoBrain functional
offline. Each fallback produces the same output schema as the router path so
callers cannot tell the difference.

The patterns below are deliberately simple heuristics (keyword rules,
manufacturer schedules, depreciation curves). They are the *fallback*, not the
primary model — the router path is used whenever it is available.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

# --- Diagnostics ---------------------------------------------------------

_SEVERITY_RULES: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"check engine|misfire|overheat|smoke|stall|limp", re.I), "high",
     "A warning light, misfire or overheating points to a drivability issue. Do not delay."),
    (re.compile(r"brake|squeal|grind|pulse", re.I), "high", "Brake noises are safety-critical. Inspect pads and rotors."),
    (re.compile(r"tick|knock|rattl", re.I), "medium", "Engine top-end noise. Likely hydraulic lifters or timing chain wear."),
    (re.compile(r"vibrat|shake|wobble", re.I), "medium", "Vibration at speed suggests wheel balance, suspension bushes or drive shaft."),
    (re.compile(r"leak|drip|puddle|smell|odour", re.I), "medium", "Fluid leak. Identify fluid colour to isolate the system."),
    (re.compile(r"slow|lag|rough idle|surging", re.I), "medium", "Performance complaint. Check fuel delivery and intake."),
    (re.compile(r"noise|hum|whine|buzz", re.I), "low", "Auxiliary noise. Check bearings, alternator and power steering."),
    (re.compile(r"rattle|creak|squeak", re.I), "low", "Trim or suspension creaks. Typically non-critical."),
]

_OBD_RULES: list[tuple[str, str, str, list[str], float]] = [
    ("P030", "Misfire detected", "Cylinder misfire — coil, plug or injector.",
     ["Ignition coil", "Spark plugs"], 250.0),
    ("P042", "Catalyst efficiency low", "Catalytic converter underperforming.",
     ["O2 sensor", "Catalytic converter"], 900.0),
    ("P0171", "Fuel trim lean", "System running lean — vacuum leak or MAF.",
     ["MAF sensor", "Vacuum lines"], 180.0),
    ("P0101", "MAF circuit range", "MAF sensor reading out of range.",
     ["MAF sensor"], 150.0),
    ("P0401", "EGR flow insufficient", "EGR valve clogged.",
     ["EGR valve", "EGR gasket"], 220.0),
    ("P0455", "EVAP leak large", "Fuel vapour leak — cap or purge valve.",
     ["Fuel cap", "Purge valve"], 60.0),
]

_PART_COSTS: dict[str, float] = {
    "brake pads": 120.0, "brake rotors": 260.0, "spark plugs": 90.0,
    "ignition coil": 140.0, "oil filter": 25.0, "air filter": 45.0,
    "fuel pump": 320.0, "alternator": 480.0, "battery": 220.0,
    "starter": 300.0, "timing belt": 420.0, "water pump": 290.0,
    "shock absorber": 210.0, "tyres": 400.0, "windscreen wipers": 30.0,
    "catalytic converter": 850.0, "o2 sensor": 140.0, "maf sensor": 150.0,
    "egr valve": 210.0, "purge valve": 60.0, "thermostat": 90.0,
    "radiator": 340.0, "cv joint": 180.0, "wheel bearing": 160.0,
}

_LABOUR = 120.0  # $/hr default

_PART_NUMBERS: dict[str, str] = {
    "ignition coil": "DENSO 90919-02247",
    "spark plugs": "NGK BKR6EIX",
    "brake pads": "BENDIX DB1479",
    "brake rotors": "DBA 2852",
    "oil filter": "RYCO Z89A",
    "air filter": "RYCO A1528",
    "fuel pump": "BOSCH 0580314052",
    "alternator": "BOSCH 0986043770",
    "battery": "CENTURY 55D23L",
    "starter": "DENSO 428000-3630",
    "timing belt": "GATES KTB320",
    "water pump": "GMB EAA146",
    "shock absorber": "KYB 341240",
    "tyres": "MICHELIN PRIMACY 4",
    "catalytic converter": "WALKER 17350",
    "o2 sensor": "DENSO 234-4505",
    "maf sensor": "DENSO 197-6030",
    "egr valve": "DELPHI EG14658",
    "purge valve": "STANDARD VAP110",
    "thermostat": "TAMA 3151-85",
    "radiator": "NISSENS 65017",
    "cv joint": "GKN 307004",
    "wheel bearing": "TIMKEN 513084",
}


def _parts_with_numbers(parts: list[str]) -> list[dict]:
    return [
        {"name": p, "part_number": _PART_NUMBERS.get(p.lower().strip())}
        for p in parts
    ]


def diagnose_fallback(symptoms: str, vehicle: dict | None = None, obd_codes: list[str] | None = None) -> dict:
    obd_codes = obd_codes or []
    items = []

    for code, label, cause, parts, part_cost in _OBD_RULES:
        if any(code in (c or "").upper() for c in obd_codes):
            items.append(_diag_item(label, cause, 0.92, "high", parts, part_cost))

    symptom_used = False
    for pattern, severity, note in _SEVERITY_RULES:
        if pattern.search(symptoms):
            items.append(_diag_item(note.split(" — ")[0], note, 0.75, severity,
                                    _parts_for(symptoms), _cost_for(symptoms)))
            symptom_used = True
            break

    if not items:
        items.append(_diag_item(
            "General condition check", "No specific fault pattern matched. Run a full systems scan.",
            0.5, "low", [], None,
        ))

    parts_needed = sorted({p for it in items for p in it["parts_needed"]})
    est = sum(it["estimated_cost"] or 0.0 for it in items)
    return {
        "summary": items[0]["cause"] if items else "No fault pattern identified.",
        "severity": max((it["severity"] for it in items), key=lambda s: _sev_rank(s)),
        "estimated_cost": est if est else None,
        "cost_range": [round(est * 0.8, 0), round(est * 1.4, 0)] if est else None,
        "items": items,
        "parts_needed": parts_needed,
        "recommended_actions": [
            "Book an inspection to confirm the diagnosis",
            "Capture and log OBD codes if available",
            "Review the proposed parts list before purchasing",
        ],
        "model": "rule-based-fallback",
    }


def _diag_item(cause, note, confidence, severity, parts, cost) -> dict:
    return {
        "cause": cause, "confidence": confidence, "severity": severity,
        "parts_needed": parts,
        "parts": _parts_with_numbers(parts),
        "repair_notes": note,
        "estimated_cost": cost,
        "cost_range": [round(cost * 0.8, 0), round(cost * 1.4, 0)] if cost else None,
    }


def _parts_for(symptoms: str) -> list[str]:
    hits = [p for p in _PART_COSTS if p in symptoms.lower()]
    return hits or ["Inspection required"]


def _cost_for(symptoms: str) -> float | None:
    hits = [p for p in _PART_COSTS if p in symptoms.lower()]
    return sum(_PART_COSTS[p] for p in hits) + _LABOUR if hits else None


def _sev_rank(s: str) -> int:
    return {"low": 0, "medium": 1, "high": 2, "critical": 3}.get(s, 0)


# --- Service prediction --------------------------------------------------

# interval_km, interval_months for common service types
_SCHEDULE: dict[str, tuple[int, int]] = {
    "oil_change": (10000, 12),
    "tyre_rotation": (10000, 12),
    "air_filter": (30000, 24),
    "brake_fluid": (50000, 24),
    "coolant": (100000, 48),
    "transmission": (80000, 48),
    "spark_plugs": (60000, 48),
    "timing_belt": (100000, 60),
    "brake_pads": (40000, 36),
    "battery": (60000, 48),
    "scheduled": (20000, 12),
}

# make-specific interval adjustments (multiplier)
_MAKE_MULT: dict[str, float] = {
    "toyota": 0.9, "honda": 0.9, "mazda": 0.95, "ford": 1.0,
    "holden": 1.0, "bmw": 1.1, "audi": 1.1, "mercedes": 1.1,
    "land rover": 1.2, "jaguar": 1.2, "subaru": 0.95,
}


def predict_service_fallback(payload: dict) -> dict:
    make = (payload.get("make") or "").lower()
    service_type = payload.get("service_type", "oil_change")
    interval_km, interval_months = _SCHEDULE.get(service_type, _SCHEDULE["scheduled"])
    interval_km = int(interval_km * _MAKE_MULT.get(make, 1.0))

    odo = int(payload.get("odometer_km") or 0)
    last_km = payload.get("last_service_km")
    last_days = payload.get("last_service_days_ago")

    basis = []
    next_km = last_km + interval_km if last_km else ((odo // interval_km) + 1) * interval_km
    due_in_km = max(next_km - odo, 0)

    if last_days is not None:
        due_date = date.today() + timedelta(days=max(interval_months * 30 - last_days, 0))
        due_in_days = max(interval_months * 30 - last_days, 0)
        basis.append("time-based")
    else:
        due_date = date.today() + timedelta(days=interval_months * 30)
        due_in_days = interval_months * 30
        basis.append("calendar-based")

    confidence = 0.8 if last_km or last_days is not None else 0.6
    reason = (
        f"Manufacturer interval for {service_type.replace('_', ' ')} on "
        f"{make or 'this vehicle'} is ~{interval_km:,} km / {interval_months} months. "
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
    }


# --- Resale value ---------------------------------------------------------

_BASE_VALUES: dict[str, dict[str, float]] = {
    # make -> {model_token: base_value}
    "toyota": {"camry": 26000.0, "corolla": 22000.0, "hilux": 38000.0, "land cruiser": 75000.0},
    "mazda": {"cx-5": 30000.0, "mazda3": 24000.0, "bt-50": 35000.0},
    "ford": {"ranger": 38000.0, "focus": 18000.0, "mustang": 55000.0},
    "holden": {"commodore": 22000.0},
    "bmw": {"3 series": 42000.0, "5 series": 52000.0, "m3": 85000.0},
    "audi": {"a4": 40000.0, "a3": 33000.0},
    "subaru": {"outback": 32000.0, "forester": 30000.0, "wrx": 38000.0},
    "honda": {"civic": 24000.0, "accord": 27000.0},
}


def estimate_value_fallback(payload: dict) -> dict:
    vehicle = payload.get("vehicle", {})
    make = (vehicle.get("make") or "").lower()
    model = (vehicle.get("model") or "").lower()
    year = int(vehicle.get("year") or date.today().year)
    odo = int(vehicle.get("odometer_km") or 0)
    condition = (vehicle.get("condition") or "good").lower()

    base = 24000.0
    for model_token, value in _BASE_VALUES.get(make, {}).items():
        if model_token in model:
            base = value
            break

    age = max(date.today().year - year, 0)
    value = base * (0.85 ** min(age, 15))

    # odometer: assume 15k km/yr
    expected_km = age * 15000
    km_ratio = odo / max(expected_km, 1)
    if km_ratio > 1:
        value *= max(1.0 - (km_ratio - 1) * 0.12, 0.5)
    else:
        value *= 1.0 + (1 - km_ratio) * 0.04

    cond_mult = {"excellent": 1.08, "good": 1.0, "fair": 0.88, "poor": 0.72}.get(condition, 1.0)
    value *= cond_mult

    # service history uplift
    if payload.get("service_count", 0) >= 5:
        value *= 1.03
    if payload.get("total_service_cost", 0) > 0:
        value *= 1.02

    mods = payload.get("mods", [])
    mods_value = sum(_mod_value_impact(m) for m in mods)
    value += mods_value

    low, high = value * 0.92, value * 1.08
    recommendations = [
        "Maintain full service history — documented records add ~5%.",
        "Refurbish body paint chips before sale.",
        "Keep OEM parts where resale matters most.",
    ]
    if condition in ("fair", "poor"):
        recommendations.insert(0, "Address outstanding repairs before selling.")
    if mods:
        recommendations.insert(0, "Highlight documented, reversible modifications in the listing.")

    return {
        "estimated_value": round(value, 0),
        "low": round(low, 0),
        "high": round(high, 0),
        "currency": "AUD",
        "factors": {
            "base_value": base, "age_years": age, "odometer": odo,
            "condition": condition, "service_records": payload.get("service_count", 0),
            "modification_value_delta": round(mods_value, 0),
        },
        "recommendations": recommendations,
        "trend": [],
        "model": "rule-based-fallback",
    }


def _mod_value_impact(mod: dict) -> float:
    cat = (mod.get("category") or "").lower()
    cost = float(mod.get("cost") or 0.0)
    if cat in ("performance", "engine", "exhaust", "suspension"):
        return cost * 0.3 if cost else 300.0
    if cat in ("audio", "visual", "interior"):
        return cost * 0.1 if cost else -100.0
    return cost * 0.15 if cost else 0.0


# --- Mod impact -----------------------------------------------------------

_MOD_IMPACT: dict[str, tuple[str, float, str]] = {
    "performance": ("Performance-focused upgrade; typically improves power output but can increase running costs.", 8.0, "Minor"),
    "engine": ("Engine modification; significant potential gain with reliability caveats.", 9.0, "Medium"),
    "exhaust": ("Exhaust upgrade; modest power gain, changes noise and emissions behaviour.", 6.0, "Minor"),
    "suspension": ("Suspension upgrade; improves handling, can reduce ride comfort.", 5.0, "Medium"),
    "brakes": ("Brake upgrade; improves safety and track performance.", 6.0, "None"),
    "audio": ("Audio system; entertainment value, minimal mechanical impact.", 2.0, "None"),
    "visual": ("Visual upgrade; cosmetic only.", 1.0, "None"),
    "interior": ("Interior upgrade; comfort and convenience.", 1.0, "None"),
    "exterior": ("Exterior upgrade; cosmetic value impact varies.", 2.0, "None"),
    "other": ("General modification; impact depends on installation quality.", 3.0, "Minor"),
}


def mod_impact_fallback(payload: dict) -> dict:
    cat = (payload.get("category") or "other").lower()
    summary, score, reliability = _MOD_IMPACT.get(cat, _MOD_IMPACT["other"])
    name = payload.get("name") or "This modification"
    value_impact = _mod_value_impact({"category": cat, "cost": payload.get("cost")})
    return {
        "summary": f"{name}: {summary}",
        "performance_score": score,
        "value_impact": value_impact,
        "reliability_impact": reliability,
        "model": "rule-based-fallback",
    }


# --- OCR / document extraction ---------------------------------------------

_VENDOR_HINTS = ["autobarn", "supercheap", "repco", "bunnings", "kmart", "harley davidson",
                 "toyota", "ford", "nissan", "mitsubishi", "penrite", "castrol"]

_ITEM_HINTS = {
    "oil": ("Oil", "part", 0.0), "filter": ("Filter", "part", 25.0),
    "brake": ("Brake pad", "part", 120.0), "rotor": ("Brake rotor", "part", 260.0),
    "battery": ("Battery", "part", 220.0), "wiper": ("Wiper blades", "part", 30.0),
    "spark": ("Spark plugs", "part", 90.0), "coolant": ("Coolant", "part", 45.0),
    "labour": ("Labour", "labour", 0.0), "service": ("Service", "labour", 150.0),
    "diagnostic": ("Diagnostic fee", "labour", 90.0),
}


def extract_receipt_fallback(text: str, content_type: str = "") -> dict:
    vendor = None
    for v in _VENDOR_HINTS:
        if v.lower() in text.lower():
            vendor = v.title()
            break

    items: list[dict] = []
    total = tax = None
    for line in text.splitlines():
        low = line.lower()
        for hint, (name, kind, cost) in _ITEM_HINTS.items():
            if hint in low and name.lower() not in [i["name"].lower() for i in items]:
                qty = 1
                cost_val = cost
                m = re.search(r"(\d+(?:\.\d{2})?)\s*$", line)
                if m:
                    cost_val = float(m.group(1))
                items.append({"kind": kind, "name": name, "quantity": qty, "unit_cost": cost_val})
                break
        m = re.search(r"total\s*[:\$]?\s*(\d+(?:\.\d{2})?)", low)
        if m and total is None:
            total = float(m.group(1))

    if not items and total:
        items.append({"kind": "labour", "name": "Service items", "quantity": 1, "unit_cost": total})

    next_service = "Routine scheduled service"
    if "oil" in text.lower() and "filter" in text.lower():
        next_service = "Oil and filter service"

    return {
        "vendor": vendor,
        "invoice_date": _extract_date(text),
        "total": total,
        "tax": tax,
        "currency": "AUD",
        "items": items,
        "next_recommended_service": next_service,
        "warranty_notes": "Parts warranty: 12 months on new components" if any(
            i["kind"] == "part" for i in items
        ) else None,
        "model": "rule-based-fallback",
    }


def _extract_date(text: str) -> str | None:
    m = re.search(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", text)
    return m.group(1) if m else None
