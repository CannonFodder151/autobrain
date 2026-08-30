"""Deterministic diagnostics fallback (symptom + OBD rules)."""

from __future__ import annotations

import re

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

# symptom keyword -> likely parts, used to enrich parts/cost estimates when the
# symptom text names a symptom but not the part.
_SYMPTOM_PARTS: dict[str, list[str]] = {
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

_OBD_RULES: list[tuple[str, str, str, list[str], float]] = [
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

_PART_COSTS: dict[str, float] = {
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
        {"name": p, "part_number": _PART_NUMBERS.get(p.lower().strip())}
        for p in parts
    ]


def diagnose_fallback(symptoms: str, vehicle: dict | None = None, obd_codes: list[str] | None = None) -> dict:
    obd_codes = obd_codes or []
    items = []

    for code, label, cause, parts, part_cost in _OBD_RULES:
        if any(code in (c or "").upper() for c in obd_codes):
            items.append(_diag_item(label, cause, 0.92, "high", parts, part_cost))

    low = symptoms.lower()
    matched = []
    for pattern, severity, note in _SEVERITY_RULES:
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
    low = symptoms.lower()
    hits = [p for p in _PART_COSTS if p in low]
    for kw, parts in _SYMPTOM_PARTS.items():
        if kw in low:
            hits.extend(p for p in parts if p not in hits)
    return hits or ["Inspection required"]


def _cost_for(symptoms: str) -> float | None:
    parts = [p for p in _parts_for(symptoms) if p != "Inspection required"]
    return sum(_PART_COSTS[p] for p in parts) + _LABOUR if parts else None


def _sev_rank(s: str) -> int:
    return {"low": 0, "medium": 1, "high": 2, "critical": 3}.get(s, 0)
