"""Deterministic resale-value fallback (AU market anchors + RRP depreciation)."""

from __future__ import annotations

from datetime import date

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
