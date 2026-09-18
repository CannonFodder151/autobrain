"""Deterministic diagnostics fallback (symptom + OBD rules)."""

from __future__ import annotations

import re

_SEVERITY_RULES: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"check engine|misfire|overheat|smoke|stall|limp|no power|hesitation", re.I), "high",
     "A warning light, misfire or overheating points to a drivability issue. Do not delay."),
    (re.compile(r"brake|squeal|grind|pulse|pedal goes|spongy|soft pedal", re.I), "high",
     "Brake noises or pedal feel issues are safety-critical. Inspect pads and rotors."),
    (re.compile(r"won'?t start|no start|no crank|clicking|turns over but|cranks but", re.I), "high",
     "Starting failure. Check battery voltage, starter motor and fuel delivery."),
    (re.compile(r"tick|knock|rattl|detonation|pinging", re.I), "medium",
     "Engine top-end noise. Likely hydraulic lifters or timing chain wear."),
    (re.compile(r"vibrat|shake|wobble|shudder|pulling|drift", re.I), "medium",
     "Vibration suggests wheel balance, suspension bushes or drive shaft."),
    (re.compile(r"leak|drip|puddle|smell|odour|fluid leak", re.I), "medium",
     "Fluid leak. Identify fluid colour to isolate the system."),
    (re.compile(r"slow|lag|rough idle|surging|hesitation|jerking", re.I), "medium",
     "Performance complaint. Check fuel delivery and intake."),
    (re.compile(r"noise|hum|whine|buzz|clunk|thud", re.I), "low",
     "Auxiliary noise. Check bearings, alternator and power steering."),
    (re.compile(r"rattle|creak|squeak|groan|chirp", re.I), "low",
     "Trim or suspension creaks. Typically non-critical."),
    (re.compile(r"battery|alternator|charging|dimming|dead battery", re.I), "high",
     "Electrical charging issue. Check alternator output and battery health."),
    (re.compile(r"steering|rack|power steer|hard to steer", re.I), "medium",
     "Steering issue. Inspect rack, pump and fluid level."),
    (re.compile(r"ac |air cond|compressor|warm air|blow hot", re.I), "medium",
     "Air conditioning issue. Check refrigerant level and compressor operation."),
    (re.compile(r"transmission|shif|gearbox|slipping|delayed shift", re.I), "high",
     "Transmission concern. Inspect fluid level and condition."),
    (re.compile(r"exhaust|fumes|loud|cat|silencer|manifold", re.I), "medium",
     "Exhaust system noise or leak. Inspect manifold and converter."),
    (re.compile(r"coolant|antifreeze|thermostat|reservoir|overheating temp", re.I), "high",
     "Cooling system issue. Check coolant level, thermostat and radiator."),
]

# symptom keyword -> likely parts, used to enrich parts/cost estimates when the
# symptom text names a symptom but not the part.
_SYMPTOM_PARTS: dict[str, list[str]] = {
    "misfire": ["spark plugs", "ignition coil"],
    "rough idle": ["spark plugs", "ignition coil", "maf sensor"],
    "overheat": ["thermostat", "radiator", "water pump"],
    "no start": ["battery", "starter"],
    "no crank": ["battery", "starter"],
    "clicking": ["battery", "starter"],
    "brake": ["brake pads", "brake rotors"],
    "squeal": ["brake pads"],
    "grind": ["brake rotors"],
    "vibrat": ["tyres", "wheel bearing"],
    "leak": ["thermostat", "radiator", "water pump"],
    "smoke": ["engine oil", "valve cover gasket", "piston rings"],
    "transmission": ["transmission fluid", "transmission service"],
    "whine": ["wheel bearing", "power steering pump"],
    "battery": ["battery", "alternator"],
    "crank": ["battery", "starter"],
    "steering": ["power steering pump", "steering rack"],
    "ac": ["ac compressor", "refrigerant"],
    "air cond": ["ac compressor", "refrigerant"],
    "exhaust": ["catalytic converter", "muffler"],
    "coolant": ["thermostat", "radiator", "water pump"],
    "oil leak": ["valve cover gasket", "oil pan gasket", "rear main seal"],
    "shift": ["transmission fluid", "transmission filter", "shift solenoid"],
    "clutch": ["clutch kit", "slave cylinder", "master cylinder"],
    "timing": ["timing belt", "water pump", "tensioner"],
    "check engine": ["oxygen sensor", "catalytic converter", "maf sensor"],
}

_OBD_RULES: list[tuple[str, str, str, list[str], float]] = [
    # Misfire codes
    ("P0300", "Random/multiple cylinder misfire", "Random misfire — coil, plug, injector or vacuum leak.",
     ["Ignition coil", "Spark plugs", "Fuel injector"], 300.0),
    ("P030", "Misfire detected", "Cylinder misfire — coil, plug or injector.",
     ["Ignition coil", "Spark plugs"], 250.0),
    ("P0301", "Misfire detected (Cylinder 1)", "Cylinder 1 misfire — coil, plug or injector.",
     ["Ignition coil", "Spark plugs"], 250.0),
    # Catalyst / O2 sensor
    ("P0420", "Catalyst efficiency below threshold (Bank 1)", "Catalytic converter underperforming — O2 sensor or cat.",
     ["O2 sensor", "Catalytic converter"], 900.0),
    ("P0430", "Catalyst efficiency below threshold (Bank 2)", "Catalytic converter underperforming — O2 sensor or cat.",
     ["O2 sensor", "Catalytic converter"], 900.0),
    ("P042", "Catalyst efficiency low", "Catalytic converter underperforming.",
     ["O2 sensor", "Catalytic converter"], 900.0),
    ("P0130", "O2 sensor circuit (Bank 1 Sensor 1)", "O2 sensor heater or signal fault.",
     ["O2 sensor"], 140.0),
    ("P0135", "O2 sensor heater (Bank 1 Sensor 1)", "O2 sensor heater circuit.",
     ["O2 sensor"], 140.0),
    ("P0141", "O2 sensor heater (Bank 1 Sensor 2)", "Downstream O2 sensor heater.",
     ["O2 sensor"], 140.0),
    # Fuel trim
    ("P0171", "Fuel trim lean (Bank 1)", "System running lean — vacuum leak or MAF.",
     ["MAF sensor", "Vacuum lines"], 180.0),
    ("P0172", "Fuel trim rich (Bank 1)", "System running rich — injector or MAF.",
     ["MAF sensor", "Fuel injectors"], 220.0),
    ("P0174", "Fuel trim lean (Bank 2)", "System running lean — vacuum leak or MAF.",
     ["MAF sensor", "Vacuum lines"], 180.0),
    ("P0175", "Fuel trim rich (Bank 2)", "System running rich — injector or MAF.",
     ["MAF sensor", "Fuel injectors"], 220.0),
    # MAF
    ("P0101", "MAF circuit range/performance", "MAF sensor reading out of range.",
     ["MAF sensor"], 150.0),
    ("P0102", "MAF circuit low input", "MAF sensor signal low — sensor or wiring.",
     ["MAF sensor"], 150.0),
    ("P0103", "MAF circuit high input", "MAF sensor signal high — sensor or wiring.",
     ["MAF sensor"], 150.0),
    # EGR
    ("P0401", "EGR flow insufficient", "EGR valve clogged.",
     ["EGR valve", "EGR gasket"], 220.0),
    ("P0402", "EGR flow excessive", "EGR valve stuck open.",
     ["EGR valve"], 220.0),
    ("P0403", "EGR circuit malfunction", "EGR control circuit fault.",
     ["EGR valve", "EGR solenoid"], 200.0),
    # EVAP
    ("P0441", "EVAP purge flow incorrect", "Purge valve or charcoal canister flow fault.",
     ["Purge valve", "Charcoal canister"], 160.0),
    ("P0442", "EVAP leak detected (small)", "Small EVAP leak — gas cap or purge valve.",
     ["Fuel cap", "Purge valve"], 60.0),
    ("P0455", "EVAP leak detected (large)", "Large EVAP leak — cap or purge valve.",
     ["Fuel cap", "Purge valve"], 60.0),
    ("P0456", "EVAP leak detected (very small)", "Very small EVAP leak.",
     ["Fuel cap"], 50.0),
    # Crankshaft / Camshaft position
    ("P0335", "Crankshaft position sensor A circuit", "No crankshaft signal — sensor or wiring.",
     ["Crankshaft position sensor"], 220.0),
    ("P0336", "Crankshaft position sensor A range", "Crankshaft sensor signal erratic.",
     ["Crankshaft position sensor"], 220.0),
    ("P0340", "Camshaft position sensor A circuit", "No camshaft signal — sensor or wiring.",
     ["Camshaft position sensor"], 220.0),
    # Throttle / TPS
    ("P0121", "TPS circuit range/performance", "Throttle position sensor signal out of range.",
     ["Throttle position sensor"], 180.0),
    ("P0221", "TPS circuit B range", "Throttle position sensor B signal out of range.",
     ["Throttle position sensor"], 180.0),
    # Idle control
    ("P0505", "Idle control system", "Idle air control valve malfunction.",
     ["Idle air control valve"], 180.0),
    ("P0506", "Idle RPM lower than expected", "Idle too low — IAC or vacuum leak.",
     ["Idle air control valve", "Vacuum lines"], 160.0),
    ("P0507", "Idle RPM higher than expected", "Idle too high — IAC or vacuum leak.",
     ["Idle air control valve", "Vacuum lines"], 160.0),
    # Transmission
    ("P0700", "Transmission fault", "PCM requesting transmission control service.",
     ["Transmission service", "Transmission fluid"], 350.0),
    ("P0730", "Incorrect gear ratio", "Transmission slipping or sensor fault.",
     ["Transmission fluid", "Shift solenoid"], 400.0),
    ("P0740", "Torque converter clutch circuit", "TCC solenoid or wiring.",
     ["Shift solenoid", "Transmission fluid"], 300.0),
    ("P0750", "Shift solenoid A", "Shift solenoid A malfunction.",
     ["Shift solenoid"], 250.0),
    ("P0760", "Shift solenoid B", "Shift solenoid B malfunction.",
     ["Shift solenoid"], 250.0),
    # Knock sensor
    ("P0325", "Knock sensor 1 circuit", "Knock sensor fault.",
     ["Knock sensor"], 150.0),
    ("P0330", "Knock sensor 2 circuit", "Knock sensor fault.",
     ["Knock sensor"], 150.0),
    # Coolant temp
    ("P0115", "ECT sensor circuit", "Coolant temp sensor circuit fault.",
     ["Coolant temp sensor"], 100.0),
    ("P0117", "ECT circuit low", "Coolant temp sensor signal low.",
     ["Coolant temp sensor"], 100.0),
    ("P0118", "ECT circuit high", "Coolant temp sensor signal high.",
     ["Coolant temp sensor"], 100.0),
    ("P0128", "Coolant thermostat rationality", "Thermostat stuck open.",
     ["Thermostat"], 90.0),
    # System voltage
    ("P0562", "System voltage low", "Charging system — alternator or battery.",
     ["Alternator", "Battery"], 480.0),
    ("P0563", "System voltage high", "Voltage regulator / alternator fault.",
     ["Alternator"], 480.0),
    # Immobilizer
    ("P0633", "Immobilizer key not programmed", "Key programming required.",
     ["Key programming"], 200.0),
    # Turbo / boost
    ("P0234", "Turbo boost overlimit", "Boost control — wastegate or solenoid.",
     ["Boost control solenoid", "Wastegate"], 300.0),
    ("P0299", "Turbo boost underlimit", "Boost leak or wastegate stuck.",
     ["Boost control solenoid", "Wastegate", "Intercooler hose"], 300.0),
]

_PART_COSTS: dict[str, float] = {
    # Brakes
    "brake pads": 120.0, "brake rotors": 260.0, "brake caliper": 350.0,
    "brake shoes": 90.0, "brake line": 60.0, "brake fluid": 25.0,
    # Ignition & electrical
    "spark plugs": 90.0, "ignition coil": 140.0,
    "battery": 220.0, "alternator": 480.0, "starter motor": 300.0,
    "starter": 300.0, "crankshaft position sensor": 180.0,
    "camshaft position sensor": 180.0,
    # Filters
    "oil filter": 25.0, "air filter": 45.0, "fuel filter": 40.0,
    "cabin filter": 30.0, "cabin air filter": 30.0,
    # Fluids
    "engine oil": 80.0, "transmission fluid": 180.0, "coolant": 45.0,
    "brake fluid": 25.0, "power steering fluid": 30.0,
    # Suspension & steering
    "shock absorber": 210.0, "strut": 250.0, "ball joint": 80.0,
    "tie rod end": 60.0, "tie rod": 60.0, "wheel bearing": 160.0,
    "control arm": 200.0, "sway bar link": 40.0,
    # Drive train
    "clutch kit": 800.0, "cv joint": 180.0, "cv axle": 250.0,
    "drive belt": 80.0, "serpentine belt": 80.0, "timing belt": 420.0,
    "timing belt kit": 650.0, "water pump": 290.0,
    # Exhaust
    "catalytic converter": 850.0, "muffler": 350.0, "exhaust": 300.0,
    "o2 sensor": 140.0, "oxygen sensor": 140.0,
    # Cooling
    "radiator": 340.0, "thermostat": 90.0,
    "coolant hose": 50.0, "radiator hose": 50.0,
    # Sensors & electronics
    "maf sensor": 150.0, "map sensor": 120.0, "knock sensor": 150.0,
    "throttle position sensor": 180.0, "coolant temp sensor": 100.0,
    "idle air control valve": 180.0, "shift solenoid": 250.0,
    # EGR & EVAP
    "egr valve": 210.0, "egr gasket": 30.0, "purge valve": 60.0,
    "charcoal canister": 180.0, "fuel cap": 20.0,
    # Fuel system
    "fuel pump": 320.0, "fuel injectors": 340.0, "fuel injector": 340.0,
    "fuel pressure regulator": 180.0,
    # Engine mechanical
    "valve cover gasket": 90.0, "head gasket": 1200.0,
    "oil pan gasket": 180.0, "rear main seal": 400.0,
    "piston rings": 800.0, "timing chain": 350.0,
    # Turbo
    "turbocharger": 1200.0, "boost control solenoid": 150.0,
    "wastegate": 200.0, "intercooler hose": 80.0,
    # AC
    "ac compressor": 650.0, "ac condenser": 350.0,
    "refrigerant": 120.0, "ac receiver drier": 80.0,
    # Steering
    "power steering pump": 380.0, "steering rack": 700.0,
    "power steering rack": 700.0,
    # Tyres & wheels
    "tyres": 400.0, "tyre": 200.0,
    # Wipers
    "wiper blades": 30.0, "wiper blade": 30.0,
    # Body
    "side mirror": 180.0, "wing mirror": 180.0, "bumper": 400.0,
    # Services
    "transmission service": 380.0, "transmission flush kit": 180.0,
}

_LABOUR = 120.0  # $/hr default

_PART_NUMBERS: dict[str, str] = {
    # Ignition
    "ignition coil": "DENSO 90919-02247",
    "spark plugs": "NGK BKR6EIX",
    # Brakes
    "brake pads": "BENDIX DB1479",
    "brake rotors": "DBA 2852",
    "brake caliper": "DBA SL4138",
    "brake shoes": "BENDIX DB1250",
    # Filters
    "oil filter": "RYCO Z89A",
    "air filter": "RYCO A1528",
    "fuel filter": "BOSCH F026407010",
    "cabin air filter": "RYCO ACF185P",
    "cabin filter": "RYCO ACF185P",
    # Fuel system
    "fuel pump": "BOSCH 0580314052",
    "fuel injectors": "BOSCH 0280158126",
    "fuel injector": "BOSCH 0280158126",
    # Electrical
    "alternator": "BOSCH 0986043770",
    "battery": "CENTURY 55D23L",
    "starter": "DENSO 428000-3630",
    "starter motor": "DENSO 428000-3630",
    # Timing
    "timing belt": "GATES KTB320",
    "timing belt kit": "GATES KTB3202",
    "timing chain": "IWIS E1149",
    "water pump": "GMB EAA146",
    # Suspension
    "shock absorber": "KYB 341240",
    "strut": "KYB 341240",
    "wheel bearing": "TIMKEN 513084",
    "ball joint": "MOOG K80149",
    "tie rod end": "MOOG EV800848",
    "control arm": "MOOG K80205",
    "sway bar link": "MOOG K80570",
    # Exhaust
    "catalytic converter": "WALKER 17350",
    "muffler": "BOSAL 185-229",
    # O2 sensors
    "o2 sensor": "DENSO 234-4505",
    "oxygen sensor": "DENSO 234-4505",
    # Intake / air
    "maf sensor": "DENSO 197-6030",
    "map sensor": "DENSO 197-6011",
    "knock sensor": "DENSO 89615-21020",
    # EGR & EVAP
    "egr valve": "DELPHI EG14658",
    "purge valve": "STANDARD VAP110",
    "charcoal canister": "ACDELCO 215-112",
    "fuel cap": "STANT 10837",
    # Cooling
    "thermostat": "TAMA 3151-85",
    "radiator": "NISSENS 65017",
    "coolant temp sensor": "DENSO 85340-20050",
    # Drive train
    "cv joint": "GKN 307004",
    "clutch kit": "SACHS 3000990073",
    # Steering
    "power steering pump": "CARDONE 21-5841",
    "steering rack": "REMAN 21-5839",
    "power steering rack": "REMAN 21-5839",
    # Turbo
    "turbocharger": "GARRETT 758665-5001S",
    "boost control solenoid": "GATES S30070",
    # Engine gaskets
    "valve cover gasket": "FEL-PRO VS50326R",
    "head gasket": "VICTOR REINZ HG-11033",
    "rear main seal": "NATIONAL 710583",
    "oil pan gasket": "FEL-PRO OS30700",
    # Engine fluids
    "engine oil": "PENRITE HPR 5",
    "transmission fluid": "VALVOLINE MAXLIFE ATF",
    "brake fluid": "BENDIX DOT4",
    "coolant": "CASTROL IPRC",
    # Services
    "transmission service": "TRANSMISSION FLUSH KIT",
    "wiper blades": "BENDIX GCT3113",
    "wiper blade": "BENDIX GCT3113",
    # AC
    "ac compressor": "DENSO DCP17115",
    "ac condenser": "DENSO 477-2128",
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
