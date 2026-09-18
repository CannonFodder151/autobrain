"""Deterministic receipt OCR fallback."""

import re

from app.ocr_utils import _extract_date

_VENDOR_HINTS = [
    # AU auto parts retailers (order matters: "supercheap" before "supercheap auto")
    "autobarn", "supercheap", "supercheap auto", "repco", "sparesbox",
    "mycar", "jax tyres", "tyrepower", "bridgestone select",
    # AU general retailers
    "bunnings", "kmart", "target", "woolworths", "coles",
    # Vehicle manufacturers (dealer service)
    "toyota", "ford", "nissan", "mitsubishi", "holden", "mazda", "honda",
    "subaru", "hyundai", "kia", "volkswagen", "bmw", "audi", "mercedes",
    "jeep", "land rover", "isuzu", "suzuki",
    # Oil / fluid brands
    "penrite", "castrol", "motul", "shell", "bosch", "ryco", "ngk",
    "dayco", "gates",
    # Motorcycle
    "harley davidson", "yamaha", "kawasaki",
]

# Item keyword -> (display name, kind, fallback cost when no line price found).
# Expanded with more part types and typical AU AUD prices.
_ITEM_HINTS = {
    # Engine fluids & filters
    "engine oil": ("Engine oil", "part", 0.0),
    "oil": ("Oil", "part", 0.0),
    "filter": ("Filter", "part", 25.0),
    "oil filter": ("Oil filter", "part", 25.0),
    "air filter": ("Air filter", "part", 35.0),
    "fuel filter": ("Fuel filter", "part", 40.0),
    "cabin filter": ("Cabin air filter", "part", 30.0),
    "cabin air filter": ("Cabin air filter", "part", 30.0),
    "coolant": ("Coolant", "part", 45.0),
    "transmission fluid": ("Transmission fluid", "part", 80.0),
    "brake fluid": ("Brake fluid", "part", 25.0),
    "power steering fluid": ("Power steering fluid", "part", 30.0),
    # Brakes
    "brake pad": ("Brake pad", "part", 120.0),
    "brake": ("Brake pad", "part", 120.0),
    "rotor": ("Brake rotor", "part", 260.0),
    "brake rotor": ("Brake rotor", "part", 260.0),
    "brake disc": ("Brake rotor", "part", 260.0),
    "brake caliper": ("Brake caliper", "part", 350.0),
    "brake shoe": ("Brake shoes", "part", 90.0),
    # Ignition & electrical
    "spark plug": ("Spark plugs", "part", 90.0),
    "spark": ("Spark plugs", "part", 90.0),
    "ignition coil": ("Ignition coil", "part", 140.0),
    "battery": ("Battery", "part", 220.0),
    "alternator": ("Alternator", "part", 480.0),
    "starter motor": ("Starter motor", "part", 300.0),
    "starter": ("Starter motor", "part", 300.0),
    # Suspension & steering
    "shock absorber": ("Shock absorber", "part", 210.0),
    "strut": ("Strut", "part", 250.0),
    "wheel bearing": ("Wheel bearing", "part", 160.0),
    "ball joint": ("Ball joint", "part", 80.0),
    "tie rod": ("Tie rod end", "part", 60.0),
    "control arm": ("Control arm", "part", 200.0),
    # Drive train
    "clutch": ("Clutch kit", "part", 800.0),
    "cv joint": ("CV joint", "part", 180.0),
    "drive belt": ("Drive belt", "part", 80.0),
    "serpentine belt": ("Serpentine belt", "part", 80.0),
    "belt": ("Drive belt", "part", 80.0),
    "timing belt": ("Timing belt", "part", 420.0),
    "timing": ("Timing belt", "part", 420.0),
    "water pump": ("Water pump", "part", 290.0),
    # Exhaust
    "catalytic converter": ("Catalytic converter", "part", 850.0),
    "muffler": ("Muffler", "part", 350.0),
    "exhaust": ("Exhaust component", "part", 300.0),
    "o2 sensor": ("O2 sensor", "part", 140.0),
    "oxygen sensor": ("O2 sensor", "part", 140.0),
    # Cooling
    "radiator": ("Radiator", "part", 340.0),
    "thermostat": ("Thermostat", "part", 90.0),
    "hose": ("Coolant hose", "part", 50.0),
    # Lighting
    "headlight": ("Headlight globe", "part", 40.0),
    "globe": ("Light globe", "part", 25.0),
    "led": ("LED bulb", "part", 35.0),
    # Wipers
    "wiper": ("Wiper blades", "part", 30.0),
    "wiper blade": ("Wiper blades", "part", 30.0),
    # Tyres
    "tyre": ("Tyre", "part", 200.0),
    "tire": ("Tyre", "part", 200.0),
    # Body / trim
    "mirror": ("Side mirror", "part", 180.0),
    "bumper": ("Bumper", "part", 400.0),
    # Sensors
    "maf sensor": ("MAF sensor", "part", 150.0),
    "knock sensor": ("Knock sensor", "part", 150.0),
    "speed sensor": ("Speed sensor", "part", 100.0),
    # Labour / services
    "labour": ("Labour", "labour", 0.0),
    "labor": ("Labour", "labour", 0.0),
    "service": ("Service", "labour", 150.0),
    "diagnostic": ("Diagnostic fee", "labour", 90.0),
    "alignment": ("Wheel alignment", "labour", 80.0),
    "balancing": ("Wheel balance", "labour", 40.0),
    "fitting": ("Fitting fee", "labour", 50.0),
    "installation": ("Installation fee", "labour", 80.0),
}

# More specific multi-word items (checked first to avoid partial-match conflicts)
_ITEM_PRIORITY = [
    "oil filter", "air filter", "fuel filter", "cabin filter", "cabin air filter",
    "engine oil", "brake pad", "brake rotor", "brake disc", "brake caliper", "brake shoe",
    "spark plug",
    "starter motor", "shock absorber", "wheel bearing",
    "ball joint", "control arm", "tie rod",
    "drive belt", "serpentine belt", "timing belt",
    "catalytic converter",
    "transmission fluid", "brake fluid", "power steering fluid",
    "oxygen sensor", "o2 sensor", "headlight",
    "water pump", "alternator", "battery",
    "radiator", "thermostat",
    "cv joint", "clutch",
]


def _find_item_in_line(low: str, items_seen_lower: list[str]) -> tuple[str, str, float, bool]:
    """Return (name, kind, cost, matched) for the first matching item hint in a line.
    Checks _ITEM_PRIORITY first to avoid ambiguous partial-word matches."""
    for hint in _ITEM_PRIORITY:
        if hint in low:
            mapped = _ITEM_HINTS.get(hint)
            if mapped:
                name, kind, cost = mapped
                if name.lower() not in items_seen_lower:
                    return name, kind, cost, True
    # Fall back to any hint (word-boundary checked to avoid partials)
    for hint, (name, kind, cost) in _ITEM_HINTS.items():
        pattern = r"(^|[^a-z0-9])" + re.escape(hint) + r"($|[^a-z0-9])"
        if re.search(pattern, low) and name.lower() not in items_seen_lower:
            return name, kind, cost, True
    return None, None, 0.0, False


def extract_receipt_fallback(text: str, content_type: str = "") -> dict:
    vendor = None
    for v in _VENDOR_HINTS:
        if v.lower() in text.lower():
            vendor = v.title()
            break

    items: list[dict] = []
    total = tax = None
    items_seen_lower: list[str] = []
    for line in text.splitlines():
        low = line.lower()
        name, kind, cost, matched = _find_item_in_line(low, items_seen_lower)
        if matched:
            qty = 1
            cost_val = cost
            m = re.search(r"(\d+(?:\.\d{2})?)\s*$", line)
            if m:
                cost_val = float(m.group(1))
            items.append({"kind": kind, "name": name, "quantity": qty, "unit_cost": cost_val})
            items_seen_lower.append(name.lower())
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
