"""Backend-level AI fallbacks (Phase 1c — AUT-3813).

Deterministic rule-based implementations for AI modules, used when the AI
gateway is unreachable. Mirrors the deterministic baselines in
``ai/app/fallbacks/`` so the backend can answer even when the gateway is
down. The gateway remains the primary path (with 9Router enrichment); these
fallbacks ensure the API never returns 503 due to gateway downtime.

Each function returns the same schema as the AI gateway's fallback.
"""

from __future__ import annotations

import re
from typing import Any


# --- Diagnostics ----------------------------------------------------------

_SEVERITY_RULES: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"check engine|misfire|overheat|smoke|stall|limp", re.I), "high",
     "A warning light, misfire or overheating points to a drivability issue. Do not delay."),
    (re.compile(r"brake|squeal|grind|pulse", re.I), "high", "Brake noises are safety-critical. Inspect pads and rotors."),
    (re.compile(r"won'?t start|no start|no crank|clicking", re.I), "high",
     "Starting failure. Check battery voltage, starter motor and fuel delivery."),
    (re.compile(r"tick|knock|rattl", re.I), "medium", "Engine top-end noise. Likely hydraulic lifters or timing chain wear."),
    (re.compile(r"vibrat|shake|wobble", re.I), "medium", "Vibration at speed suggests wheel balance, suspension bushes or drive shaft."),
    (re.compile(r"leak|drip|puddle|smell|odour", re.I), "medium", "Fluid leak. Identify fluid colour to isolate the system."),
    (re.compile(r"slow|lag|rough idle|surging", re.I), "medium", "Performance complaint. Check fuel delivery and intake."),
    (re.compile(r"noise|hum|whine|buzz", re.I), "low", "Auxiliary noise. Check bearings, alternator and power steering."),
    (re.compile(r"rattle|creak|squeak", re.I), "low", "Trim or suspension creaks. Typically non-critical."),
]

OBD_RULES: list[tuple[str, str, str, list[str], float]] = [
    ("P030", "Misfire detected", "Cylinder misfire — coil, plug or injector.",
     ["Ignition coil", "Spark plugs"], 250.0),
    ("P042", "Catalyst efficiency low", "Catalytic converter underperforming.",
     ["O2 sensor", "Catalytic converter"], 900.0),
    ("P0171", "Fuel trim lean", "System running lean — vacuum leak or MAF.",
     ["MAF sensor", "Vacuum lines"], 180.0),
    ("P0172", "Fuel trim rich", "System running rich — injector or MAF.",
     ["MAF sensor", "Fuel injectors"], 220.0),
    ("P0101", "MAF circuit range", "MAF sensor reading out of range.",
     ["MAF sensor"], 150.0),
    ("P0401", "EGR flow insufficient", "EGR valve clogged.",
     ["EGR valve", "EGR gasket"], 220.0),
    ("P0441", "EVAP purge flow", "Purge valve or charcoal canister flow fault.",
     ["Purge valve", "Charcoal canister"], 160.0),
    ("P0455", "EVAP leak large", "Fuel vapour leak — cap or purge valve.",
     ["Fuel cap", "Purge valve"], 60.0),
    ("P0335", "Crankshaft position sensor", "No crankshaft signal — sensor or wiring.",
     ["Crankshaft position sensor"], 220.0),
    ("P0700", "Transmission fault", "PCM requesting transmission control service.",
     ["Transmission service", "Transmission fluid"], 350.0),
]

PART_COSTS: dict[str, float] = {
    "brake pads": 120.0, "brake rotors": 260.0, "spark plugs": 90.0,
    "ignition coil": 140.0, "oil filter": 25.0, "air filter": 45.0,
    "fuel pump": 320.0, "alternator": 480.0, "battery": 220.0,
    "starter": 300.0, "timing belt": 420.0, "water pump": 290.0,
    "shock absorber": 210.0, "tyres": 400.0, "windscreen wipers": 30.0,
    "catalytic converter": 850.0, "o2 sensor": 140.0, "maf sensor": 150.0,
    "egr valve": 210.0, "purge valve": 60.0, "thermostat": 90.0,
    "radiator": 340.0, "cv joint": 180.0, "wheel bearing": 160.0,
    "fuel injectors": 340.0, "charcoal canister": 180.0,
    "crankshaft position sensor": 180.0, "transmission fluid": 180.0,
    "transmission service": 380.0, "valve cover gasket": 90.0,
    "power steering pump": 380.0, "engine oil": 80.0,
}

LABOUR = 120.0

SYMPTOM_PARTS: dict[str, list[str]] = {
    "misfire": ["spark plugs", "ignition coil"],
    "rough idle": ["spark plugs", "ignition coil", "maf sensor"],
    "overheat": ["thermostat", "radiator"],
    "no start": ["battery", "starter"],
    "no crank": ["battery", "starter"],
    "clicking": ["battery", "starter"],
    "brake": ["brake pads", "brake rotors"],
    "squeal": ["brake pads"],
    "grind": ["brake rotors"],
    "vibrat": ["tyres", "wheel bearing"],
    "leak": ["thermostat", "radiator"],
    "smoke": ["engine oil", "valve cover gasket"],
    "transmission": ["transmission fluid", "transmission service"],
    "whine": ["wheel bearing", "power steering pump"],
    "battery": ["battery"],
    "crank": ["battery", "starter"],
}

PART_NUMBERS: dict[str, str] = {
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
    "fuel injectors": "BOSCH 0280158126",
    "charcoal canister": "ACDELCO 215-112",
    "crankshaft position sensor": "DENSO 90919-05024",
    "transmission fluid": "VALVOLINE MAXLIFE ATF",
    "transmission service": "TRANSMISSION FLUSH KIT",
    "valve cover gasket": "FEL-PRO VS50326R",
    "power steering pump": "CARDONE 21-5841",
    "engine oil": "PENRITE HPR 5",
}


def _parts_with_numbers(parts: list[str]) -> list[dict]:
    return [
        {"name": p, "part_number": PART_NUMBERS.get(p.lower().strip())}
        for p in parts
    ]


def _sev_rank(s: str) -> int:
    return {"low": 0, "medium": 1, "high": 2, "critical": 3}.get(s, 0)


def _parts_for(symptoms: str) -> list[str]:
    low = symptoms.lower()
    hits = [p for p in PART_COSTS if p in low]
    for kw, parts in SYMPTOM_PARTS.items():
        if kw in low:
            hits.extend(p for p in parts if p not in hits)
    return hits or ["Inspection required"]


def _cost_for(symptoms: str) -> float | None:
    parts = [p for p in _parts_for(symptoms) if p != "Inspection required"]
    return sum(PART_COSTS[p] for p in parts) + LABOUR if parts else None


def _diag_item(cause, note, confidence, severity, parts, cost) -> dict:
    return {
        "cause": cause, "confidence": confidence, "severity": severity,
        "parts_needed": parts,
        "parts": _parts_with_numbers(parts),
        "repair_notes": note,
        "estimated_cost": cost,
        "cost_range": [round(cost * 0.8, 0), round(cost * 1.4, 0)] if cost else None,
    }


def diagnose_fallback(symptoms: str, vehicle: dict | None = None, obd_codes: list[str] | None = None) -> dict:
    """Deterministic diagnostics fallback (symptom + OBD rules)."""
    obd_codes = obd_codes or []
    items = []

    for code, label, cause, parts, part_cost in OBD_RULES:
        if any(code in (c or "").upper() for c in obd_codes):
            items.append(_diag_item(label, cause, 0.92, "high", parts, part_cost))

    low = symptoms.lower()
    matched = []
    for pattern, severity, note in SEVERITY_RULES:
        if pattern.search(low):
            parts = _parts_for(low)
            cost = _cost_for(low)
            matched.append(_diag_item(note.split(" — ")[0], note, 0.75, severity,
                                      parts, cost))
        if len(matched) >= 3:
            break
    items.extend(matched)

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
        "confidence": max(it["confidence"] for it in items),
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


# --- Service Prediction ---------------------------------------------------

SERVICE_INTERVALS: dict[str, dict[str, Any]] = {
    "oil": {"interval_km": 10000, "interval_months": 6},
    "logbook": {"interval_km": 15000, "interval_months": 12},
    "major": {"interval_km": 30000, "interval_months": 24},
    "tune": {"interval_km": 20000, "interval_months": 12},
    "brake": {"interval_km": 40000, "interval_months": 24},
    "tyre": {"interval_km": 50000, "interval_months": 36},
    "battery": {"interval_km": 40000, "interval_months": 36},
    "coolant": {"interval_km": 50000, "interval_months": 36},
    "transmission": {"interval_km": 60000, "interval_months": 36},
    "timing": {"interval_km": 100000, "interval_months": 60},
}


def predict_service_fallback(payload: dict) -> dict:
    """Deterministic service prediction based on manufacturer intervals."""
    service_type = payload.get("service_type", "oil").lower()
    current_km = payload.get("odometer_km", 0) or 0
    last_service_km = payload.get("last_service_km", 0) or 0
    last_service_date = payload.get("last_service_date")

    intervals = SERVICE_INTERVALS.get(service_type, SERVICE_INTERVALS["oil"])
    interval_km = intervals["interval_km"]
    interval_months = intervals["interval_months"]

    since_service_km = current_km - last_service_km
    due_in_km = max(0, interval_km - since_service_km)

    from datetime import date, timedelta
    today = date.today()
    next_due_km = current_km + due_in_km

    if last_service_date:
        try:
            last_date = date.fromisoformat(last_service_date)
            next_due_date = (last_date + timedelta(days=interval_months * 30)).isoformat()
        except (ValueError, TypeError):
            next_due_date = (today + timedelta(days=interval_months * 30)).isoformat()
    else:
        next_due_date = (today + timedelta(days=interval_months * 30)).isoformat()

    confidence = 0.85 if since_service_km < interval_km else 0.6

    return {
        "service_type": service_type,
        "interval_km": interval_km,
        "interval_months": interval_months,
        "due_in_km": due_in_km,
        "due_in_days": max(0, int((interval_months * 30) - (today - date.fromisoformat(last_service_date)).days)) if last_service_date else interval_months * 30,
        "next_due_km": next_due_km,
        "next_due_date": next_due_date,
        "confidence": confidence,
        "reason": f"Manufacturer interval for {service_type} service is {interval_km}km / {interval_months} months",
        "model": "rule-based-fallback",
    }


# --- Valuation (Resale) ---------------------------------------------------

def estimate_value_fallback(payload: dict) -> dict:
    """Deterministic valuation based on make/model/year/km heuristics."""
    make = (payload.get("make") or "").strip().lower()
    model = (payload.get("model") or "").strip().lower()
    year = payload.get("year") or 2020
    odometer_km = payload.get("odometer_km") or 150000
    condition = (payload.get("condition") or "good").lower()

    base_values: dict[str, float] = {
        "toyota": 25000, "holden": 20000, "ford": 22000, "mazda": 24000,
        "hyundai": 18000, "kia": 19000, "nissan": 20000, "subaru": 26000,
        "honda": 23000, "vw": 24000, "mercedes": 35000, "bmw": 40000,
        "audi": 38000, "volvo": 32000, "jeep": 30000, "landrover": 45000,
    }

    base_value = base_values.get(make, 22000)

    current_year = 2026
    age = max(1, current_year - year)
    depreciation = 0.85 ** age
    km_adjustment = 1.0 - (odometer_km / 200000)
    condition_adjustment = {"excellent": 1.1, "good": 1.0, "fair": 0.9, "poor": 0.8}.get(condition, 1.0)

    estimated_value = base_value * depreciation * km_adjustment * condition_adjustment
    low = estimated_value * 0.85
    high = estimated_value * 1.15

    return {
        "estimated_value": round(estimated_value),
        "low": round(low),
        "high": round(high),
        "currency": "AUD",
        "confidence": 0.65,
        "model": "rule-based-fallback",
    }


# --- Mod Impact -----------------------------------------------------------

MOD_IMPACT_RULES: dict[str, dict[str, Any]] = {
    "exhaust": {"performance": 7, "value": -2, "reliability": "Minor"},
    "suspension": {"performance": 6, "value": 5, "reliability": "Minor"},
    "intake": {"performance": 5, "value": 1, "reliability": "Minor"},
    "ecu": {"performance": 8, "value": 3, "reliability": "Medium"},
    "turbo": {"performance": 9, "value": 8, "reliability": "High"},
    "supercharger": {"performance": 9, "value": 8, "reliability": "High"},
    "brakes": {"performance": 7, "value": 4, "reliability": "None"},
    "wheels": {"performance": 3, "value": 2, "reliability": "None"},
    "tyres": {"performance": 5, "value": 1, "reliability": "None"},
    "body": {"performance": 0, "value": 3, "reliability": "None"},
    "interior": {"performance": 0, "value": 2, "reliability": "None"},
    "lights": {"performance": 1, "value": 1, "reliability": "None"},
    "audio": {"performance": 0, "value": 1, "reliability": "None"},
}


def mod_impact_fallback(payload: dict) -> dict:
    """Deterministic mod impact estimation based on category rules."""
    category = (payload.get("category") or "").lower()
    name = (payload.get("name") or "").lower()

    rules = MOD_IMPACT_RULES.get(category, MOD_IMPACT_RULES.get(name, {
        "performance": 5, "value": 0, "reliability": "Minor"
    }))

    return {
        "summary": f"{name or category} modification",
        "performance_score": rules["performance"],
        "value_impact": rules["value"],
        "reliability_impact": rules["reliability"],
        "confidence": 0.7,
        "model": "rule-based-fallback",
    }


# --- Odometer OCR ----------------------------------------------------------

def odometer_fallback(payload: dict) -> dict:
    """Deterministic odometer reading (no AI — returns None to trigger user re-entry)."""
    return {
        "odometer_km": None,
        "confidence": 0.0,
        "model": "rule-based-fallback",
        "note": "Automatic odometer reading unavailable. Please enter manually.",
    }


# --- Fuel OCR -------------------------------------------------------------

def fuel_receipt_fallback(payload: dict) -> dict:
    """Deterministic fuel receipt extraction (no AI — returns empty)."""
    return {
        "vendor": None,
        "date": None,
        "litres": None,
        "price_per_litre": None,
        "total_cost": None,
        "currency": "AUD",
        "notes": None,
        "confidence": 0.0,
        "model": "rule-based-fallback",
        "note": "Automatic fuel receipt reading unavailable. Please enter manually.",
    }


# --- Receipt OCR ----------------------------------------------------------

def receipt_fallback(payload: dict) -> dict:
    """Deterministic receipt extraction (no AI — returns empty)."""
    return {
        "vendor": None,
        "invoice_date": None,
        "total": None,
        "tax": None,
        "currency": "AUD",
        "items": [],
        "next_recommended_service": None,
        "warranty_notes": None,
        "confidence": 0.0,
        "model": "rule-based-fallback",
        "note": "Automatic receipt reading unavailable. Please enter manually.",
    }


# --- Parts Guide -----------------------------------------------------------

def parts_guide_fallback(payload: dict) -> dict:
    """Deterministic parts guide (returns empty list)."""
    return {
        "parts": [],
        "vehicle": payload.get("vehicle", {}),
        "model": payload.get("model", ""),
        "suggested_parts": [],
        "confidence": 0.0,
        "model": "rule-based-fallback",
        "note": "Automatic parts suggestion unavailable.",
    }


# --- Condition Estimation --------------------------------------------------

def condition_fallback(payload: dict) -> dict:
    """Deterministic condition estimation based on diagnostics + service history."""
    diagnostics = payload.get("diagnostics", [])
    service_count = len(payload.get("service_history", []))
    odometer_km = payload.get("odometer_km", 0) or 0

    open_issues = sum(1 for d in diagnostics if d.get("status") != "resolved")

    if open_issues > 3 or odometer_km > 200000:
        condition = "poor"
    elif open_issues > 1 or odometer_km > 150000:
        condition = "fair"
    elif service_count >= 3 or odometer_km < 50000:
        condition = "excellent"
    else:
        condition = "good"

    return {
        "condition": condition,
        "score": {"excellent": 90, "good": 75, "fair": 55, "poor": 35}.get(condition, 60),
        "summary": f"Condition assessed as {condition} based on {open_issues} open issues and {service_count} services",
        "confidence": 0.7,
        "model": "rule-based-fallback",
    }
