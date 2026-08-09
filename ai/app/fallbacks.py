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


# --- Resale value ---------------------------------------------------------

# Realistic AU used-market values (AUD) for a ~2010 model-year car with
# ~120,000 km in good condition. Values are market anchors, not new-car
# prices: 9Router enrichment may tweak advice/trend, but the deterministic
# number is the ground truth (see _AI_IMMUTABLE in router_client.py).
_BASE_VALUES: dict[str, dict[str, float]] = {
    "toyota": {"corolla": 11000.0, "camry": 12000.0, "hilux": 22000.0,
               "land cruiser": 30000.0, "landcruiser": 30000.0, "prado": 28000.0,
               "rav4": 14000.0, "86": 12000.0, "aurion": 11000.0},
    "ford": {"crown victoria": 14000.0, "crown": 14000.0, "falcon": 14000.0, "territory": 16000.0,
             "ranger": 18000.0, "mustang": 25000.0, "focus": 8000.0,
             "fiesta": 7000.0},
    "holden": {"commodore": 14000.0, "cruze": 7000.0, "captiva": 9000.0,
               "colorado": 16000.0, "astra": 7000.0},
    "mazda": {"mazda3": 9000.0, "mazda 3": 9000.0, "mazda6": 10000.0,
              "mazda 6": 10000.0, "cx-5": 12000.0, "bt-50": 15000.0, "mx-5": 15000.0},
    "nissan": {"patrol": 24000.0, "navara": 15000.0, "skyline": 18000.0,
               "xtrail": 10000.0, "gtr": 60000.0, "pulsar": 7000.0},
    "subaru": {"outback": 13000.0, "forester": 13000.0, "wrx": 15000.0,
               "impreza": 9000.0},
    "honda": {"civic": 10000.0, "accord": 11000.0, "cr-v": 12000.0, "jazz": 8000.0},
    "bmw": {"3 series": 15000.0, "3-series": 15000.0, "5 series": 17000.0,
            "5-series": 17000.0, "m3": 28000.0, "x5": 20000.0},
    "audi": {"a3": 13000.0, "a4": 15000.0, "q5": 16000.0},
    "mercedes": {"c-class": 15000.0, "e-class": 18000.0, "a-class": 12000.0,
                 "g-class": 35000.0},
    "volkswagen": {"golf": 10000.0, "polo": 8000.0, "passat": 11000.0, "tiguan": 13000.0},
    "hyundai": {"i30": 8000.0, "tucson": 10000.0, "santa fe": 11000.0},
    "kia": {"cerato": 7000.0, "sportage": 10000.0, "carnival": 12000.0},
    "mitsubishi": {"lancer": 7000.0, "outlander": 10000.0, "triton": 14000.0,
                   "pajero": 18000.0},
    "jeep": {"wrangler": 18000.0, "grand cherokee": 12000.0, "cherokee": 10000.0},
    "land rover": {"defender": 22000.0, "range rover": 25000.0, "discovery": 15000.0},
}

# Minimum fraction of the model's market anchor a vehicle can fall to.
# Cult classics / AU icons (Crown Vic, Falcon, Commodore, Patrol, LandCruiser)
# hold a high floor; generic hatches depreciate further but never to zero.
_FLOOR_RATIOS: dict[str, float] = {
    "crown victoria": 0.9, "crown": 0.9, "falcon": 0.8, "commodore": 0.8, "territory": 0.7,
    "land cruiser": 0.9, "landcruiser": 0.9, "prado": 0.85, "patrol": 0.85,
    "hilux": 0.85, "ranger": 0.8, "defender": 0.9, "gtr": 0.8, "skyline": 0.8,
    "mustang": 0.7, "wrangler": 0.8, "mx-5": 0.7, "wrx": 0.7, "g-class": 0.8,
}

_REF_YEAR = 2010  # market anchor year for _BASE_VALUES

# New-car RRP (AUD) for recent models. Used for cars the 2010-anchor model
# cannot value (current-model SUVs/utes like a 2025 Ford Everest have no
# 2010 anchor). The AI/router path may supply a more precise rrp per vehicle;
# the table is the deterministic offline baseline.
_RRP_VALUES: dict[str, dict[str, float]] = {
    "toyota": {"camry": 36000.0, "corolla": 30000.0, "hilux": 55000.0,
               "land cruiser": 120000.0, "landcruiser": 120000.0, "prado": 80000.0,
               "rav4": 45000.0, "kluger": 65000.0, "yaris": 26000.0},
    "ford": {"ranger": 55000.0, "mustang": 65000.0, "everest": 62000.0,
             "escape": 40000.0, "puma": 32000.0, "fiesta": 24000.0},
    "mazda": {"cx-5": 38000.0, "mazda3": 28000.0, "mazda 3": 28000.0,
              "bt-50": 48000.0, "cx-30": 33000.0, "mx-5": 42000.0},
    "holden": {"commodore": 45000.0, "colorado": 48000.0},
    "bmw": {"3 series": 72000.0, "3-series": 72000.0, "5 series": 95000.0,
            "5-series": 95000.0, "m3": 130000.0, "x3": 85000.0, "x5": 110000.0},
    "audi": {"a4": 65000.0, "a3": 48000.0, "q3": 55000.0, "q5": 75000.0},
    "subaru": {"outback": 45000.0, "forester": 42000.0, "wrx": 45000.0, "xv": 34000.0},
    "honda": {"civic": 36000.0, "accord": 40000.0, "cr-v": 45000.0},
    "kia": {"sportage": 40000.0, "cerato": 29000.0, "sorento": 50000.0, "picanto": 20000.0},
    "hyundai": {"tucson": 40000.0, "i30": 29000.0, "santa fe": 55000.0, "palisade": 70000.0},
    "nissan": {"xtrail": 40000.0, "patrol": 90000.0, "navara": 48000.0},
    "mitsubishi": {"outlander": 38000.0, "triton": 45000.0, "pajero sport": 50000.0,
                   "pajero": 50000.0, "asx": 30000.0},
    "volkswagen": {"golf": 40000.0, "tiguan": 45000.0, "amarok": 60000.0, "polo": 28000.0},
    "isuzu": {"d-max": 55000.0, "mux": 58000.0},
    "suzuki": {"jimny": 32000.0, "swift": 24000.0},
    "tesla": {"model 3": 55000.0, "model y": 60000.0},
}

# Age (years) -> residual fraction of RRP on the AU market.
_DEPRECIATION: dict[int, float] = {
    0: 1.00, 1: 0.92, 2: 0.85, 3: 0.78, 4: 0.71, 5: 0.65,
    6: 0.59, 7: 0.54, 8: 0.49, 9: 0.45, 10: 0.41,
}

# Cars newer than this are valued off RRP (the anchor model caps at ~15yr of
# 3%/yr premium and cannot price current models that post-date 2010).
_RRP_YEAR_MIN = _REF_YEAR + 8


def rrp_for(vehicle: dict) -> float | None:
    """Look up a new-car RRP (AUD) for a make/model from the static table."""
    make = (vehicle.get("make") or "").lower()
    model = (vehicle.get("model") or "").lower()
    for token, rrp in _RRP_VALUES.get(make, {}).items():
        if token in model:
            return rrp
    return None


def _depreciation_multiplier(age: int) -> float:
    mult = _DEPRECIATION.get(min(age, 10), _DEPRECIATION[10])
    for _ in range(10, age):
        mult *= 0.95
    return max(mult, 0.18)


def estimate_value_fallback(payload: dict, rrp: float | None = None,
                            used_price: float | None = None) -> dict:
    vehicle = payload.get("vehicle", {})
    make = (vehicle.get("make") or "").lower()
    model = (vehicle.get("model") or "").lower()
    year = int(vehicle.get("year") or _REF_YEAR)
    odo = int(vehicle.get("odometer_km") or 0)
    condition = (vehicle.get("condition") or "good").lower()

    if rrp is None:
        rrp = rrp_for(vehicle)
    use_rrp = bool(rrp) and year >= _RRP_YEAR_MIN
    age = max(date.today().year - year, 0)

    if use_rrp:
        # Modern-car path: anchor on the new-car RRP and depreciate by age.
        value = rrp * _depreciation_multiplier(age)
        expected_km = age * 15000 or 1
        km_ratio = odo / expected_km
        if age > 0:
            if km_ratio > 1:
                value *= max(1.0 - (km_ratio - 1) * 0.12, 0.5)
            else:
                value *= 1.0 + (1 - km_ratio) * 0.04
        factors: dict = {
            "rrp": round(rrp, 0), "anchor": "rrp", "age_years": age,
            "odometer": odo, "condition": condition,
        }
        known = bool(rrp_for(vehicle))
        confidence = 0.9 if known else 0.7
    else:
        base, floor = _model_market_value(make, model)
        age_delta = year - _REF_YEAR
        if age_delta >= 0:
            value = base * (1.03 ** min(age_delta, 15))
        else:
            value = base * (0.97 ** min(-age_delta, 20))
        value = max(value, base * floor)

        expected_km = max((year - _REF_YEAR) * 15000, 0) + 120000
        km_ratio = odo / max(expected_km, 1)
        if km_ratio > 1.1:
            value *= max(1.0 - (km_ratio - 1) * 0.10, 0.6)
        elif km_ratio < 0.9:
            value *= 1.0 + (0.9 - km_ratio) * 0.08

        factors = {
            "base_value": base, "floor_value": round(base * floor, 0),
            "anchor_year": _REF_YEAR, "odometer": odo,
            "condition": condition,
        }
        known = make in _BASE_VALUES and any(t in model for t in _BASE_VALUES[make])
        confidence = 0.9 if known else (0.6 if make in _BASE_VALUES else 0.5)

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
    factors["service_records"] = payload.get("service_count", 0)
    factors["modification_value_delta"] = round(mods_value, 0)

    # AI-supplied current selling price refines the estimate, clamped to a
    # sane band around the deterministic number so a bad fact can't skew it.
    if used_price and used_price > 0:
        band_low, band_high = value * 0.85, value * 1.15
        value = min(max(used_price, band_low), band_high)

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

    if payload.get("service_count") or payload.get("total_service_cost"):
        confidence = round(min(confidence + 0.05, 0.95), 2)

    return {
        "estimated_value": round(value, 0),
        "low": round(low, 0),
        "high": round(high, 0),
        "currency": "AUD",
        "confidence": confidence,
        "factors": factors,
        "recommendations": recommendations,
        "trend": [],
        "model": "rrp-depreciation" if use_rrp else "rule-based-fallback",
    }


def _model_market_value(make: str, model: str) -> tuple[float, float]:
    """Return (market_anchor, floor_ratio) for a make/model.

    Falls back to a make-level estimate, then to a generic AUD hatchback
    anchor so unknown vehicles still get a sane, non-zero number.
    """
    for token, value in _BASE_VALUES.get(make, {}).items():
        if token in model:
            return value, _FLOOR_RATIOS.get(token, 0.5)
    make_defaults = {
        "toyota": 12000.0, "ford": 12000.0, "holden": 10000.0, "mazda": 9000.0,
        "nissan": 10000.0, "subaru": 11000.0, "honda": 9000.0, "bmw": 15000.0,
        "audi": 14000.0, "mercedes": 15000.0, "volkswagen": 9000.0,
        "hyundai": 8000.0, "kia": 7000.0, "mitsubishi": 9000.0, "jeep": 12000.0,
        "land rover": 15000.0,
    }
    return make_defaults.get(make, 10000.0), 0.5


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
    known = cat in _MOD_IMPACT
    summary, score, reliability = _MOD_IMPACT.get(cat, _MOD_IMPACT["other"])
    name = payload.get("name") or "This modification"
    value_impact = _mod_value_impact({"category": cat, "cost": payload.get("cost")})
    return {
        "summary": f"{name}: {summary}",
        "performance_score": score,
        "value_impact": value_impact,
        "reliability_impact": reliability,
        "confidence": 0.9 if known else 0.5,
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

    confidence = round(min(0.4 + 0.12 * len(items), 0.95), 2) if items else 0.4

    return {
        "vendor": vendor,
        "invoice_date": _extract_date(text),
        "total": total,
        "tax": tax,
        "currency": "AUD",
        "confidence": confidence,
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
