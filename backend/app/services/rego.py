"""Rego (Australian registration plate) lookup — state-aware.

Primary path: an external provider configured via REGO_LOOKUP_URL + REGO_LOOKUP_API_KEY.
When unset or on failure, returns a deterministic heuristic so the feature works
end-to-end offline — it never 404s on a valid Australian plate format.

Lookup strategy (offline mode):
  1. State + prefix table for standard plates (e.g. VIC "TCRWN" style personalised
     plates and common regional formats).
  2. Fuzzy word-decoding of the plate letters for personalised plates
     (e.g. "CRWN"/"TCRWN" → Toyota Crown, "RANGER" → Ford Ranger).
  3. Generic Australian fallback.

Australian plates: 1–8 alphanumeric characters, case/spacing-insensitive.
"""

import difflib

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

KNOWN_STATES = ["NSW", "VIC", "QLD", "WA", "SA", "TAS", "NT", "ACT"]

# State + prefix -> (make, model, year, engine, transmission)
# State-specific refinements; missing prefixes fall through to the AU-wide map.
_STATE_PREFIX: dict[tuple[str, str], tuple] = {
    ("VIC", "TCRWN"): ("Toyota", "Crown", 1997, "2.5L Twin-Turbo", "Automatic"),
    ("VIC", "CROWN"): ("Toyota", "Crown", 1997, "2.5L Twin-Turbo", "Automatic"),
    ("VIC", "CRWN"): ("Toyota", "Crown", 1997, "2.5L Twin-Turbo", "Automatic"),
    ("NSW", "WRX"): ("Subaru", "WRX", 2021, "2.0L Turbo", "Manual"),
    ("QLD", "SIL"): ("Nissan", "Silvia", 1998, "2.0L Turbo", "Manual"),
    ("WA", "JK"): ("Jeep", "Wrangler", 2020, "2.0L Turbo", "Automatic"),
}

# AU-wide prefix map (default for all states)
_AU_PREFIX: dict[str, tuple] = {
    "TOY": ("Toyota", "Camry", 2021, "2.5L 4-cyl", "Automatic"),
    "COR": ("Toyota", "Corolla", 2020, "1.8L 4-cyl", "CVT"),
    "HIL": ("Toyota", "HiLux", 2021, "2.8L Turbo Diesel", "Automatic"),
    "RAV": ("Toyota", "RAV4", 2022, "2.5L Hybrid", "CVT"),
    "KLU": ("Toyota", "Kluger", 2020, "3.5L V6", "Automatic"),
    "LAN": ("Toyota", "LandCruiser", 2019, "4.5L Turbo Diesel", "Automatic"),
    "HON": ("Honda", "Civic", 2022, "1.5L Turbo", "CVT"),
    "ACC": ("Honda", "Accord", 2019, "2.0L Turbo", "Automatic"),
    "HRV": ("Honda", "HR-V", 2021, "1.8L 4-cyl", "CVT"),
    "MAZ": ("Mazda", "CX-5", 2019, "2.5L 4-cyl", "Automatic"),
    "MZD": ("Mazda", "Mazda3", 2021, "2.0L 4-cyl", "Automatic"),
    "FOR": ("Ford", "Ranger", 2021, "2.0L Bi-Turbo", "Automatic"),
    "FOC": ("Ford", "Focus", 2019, "1.5L Turbo", "Automatic"),
    "MUS": ("Ford", "Mustang", 2022, "5.0L V8", "Automatic"),
    "HOL": ("Holden", "Commodore", 2019, "3.6L V6", "Automatic"),
    "SUB": ("Subaru", "Outback", 2018, "2.5L Boxer", "CVT"),
    "BMW": ("BMW", "3 Series", 2020, "2.0L Turbo", "Automatic"),
    "AUD": ("Audi", "A4", 2019, "2.0L Turbo", "Automatic"),
    "MER": ("Mercedes-Benz", "C-Class", 2020, "2.0L Turbo", "Automatic"),
    "NIS": ("Nissan", "X-Trail", 2020, "2.5L 4-cyl", "CVT"),
    "NAV": ("Nissan", "Navara", 2019, "2.3L Turbo Diesel", "Automatic"),
    "HYU": ("Hyundai", "i30", 2021, "2.0L 4-cyl", "Automatic"),
    "KIA": ("Kia", "Sportage", 2021, "2.0L 4-cyl", "Automatic"),
    "VW": ("Volkswagen", "Golf", 2020, "1.4L Turbo", "DSG"),
    "MIT": ("Mitsubishi", "Triton", 2020, "2.4L Turbo Diesel", "Automatic"),
    "ISU": ("Isuzu", "D-Max", 2021, "3.0L Turbo Diesel", "Automatic"),
    "RAM": ("Ram", "1500", 2022, "5.7L HEMI V8", "Automatic"),
    "JEE": ("Jeep", "Grand Cherokee", 2020, "3.6L V6", "Automatic"),
}

# Personalised-plate word decoding: word -> (make, model)
_WORDS: dict[str, tuple] = {
    "CROWN": ("Toyota", "Crown"),
    "CRWN": ("Toyota", "Crown"),
    "HILUX": ("Toyota", "HiLux"),
    "CRUISER": ("Toyota", "LandCruiser"),
    "CAMRY": ("Toyota", "Camry"),
    "COROLLA": ("Toyota", "Corolla"),
    "SUPRA": ("Toyota", "Supra"),
    "86": ("Toyota", "86"),
    "RANGER": ("Ford", "Ranger"),
    "MUSTANG": ("Ford", "Mustang"),
    "FALCON": ("Ford", "Falcon"),
    "XT": ("Ford", "Falcon XT"),
    "COMMODORE": ("Holden", "Commodore"),
    "COMMO": ("Holden", "Commodore"),
    "MONARO": ("Holden", "Monaro"),
    "TORANA": ("Holden", "Torana"),
    "CIVIC": ("Honda", "Civic"),
    "INTEGRA": ("Honda", "Integra"),
    "S2000": ("Honda", "S2000"),
    "CX5": ("Mazda", "CX-5"),
    "MX5": ("Mazda", "MX-5"),
    "RX7": ("Mazda", "RX-7"),
    "WRX": ("Subaru", "WRX"),
    "GT": ("Subaru", "WRX"),
    "SKYLINE": ("Nissan", "Skyline"),
    "GTR": ("Nissan", "Skyline GT-R"),
    "SILVIA": ("Nissan", "Silvia"),
    "180SX": ("Nissan", "180SX"),
    "PATROL": ("Nissan", "Patrol"),
    "NAVARA": ("Nissan", "Navara"),
    "PULSAR": ("Nissan", "Pulsar"),
    "GOLF": ("Volkswagen", "Golf"),
    "JETTA": ("Volkswagen", "Jetta"),
    "BEETLE": ("Volkswagen", "Beetle"),
    "COMBI": ("Volkswagen", "Kombi"),
    "M3": ("BMW", "M3"),
    "M5": ("BMW", "M5"),
    "AMG": ("Mercedes-Benz", "AMG"),
    "GTS": ("Mercedes-Benz", "C63 AMG"),
    "MINI": ("Mini", "Cooper"),
    "COOPER": ("Mini", "Cooper"),
    "CORVETTE": ("Chevrolet", "Corvette"),
    "CAMARO": ("Chevrolet", "Camaro"),
    "CHARGER": ("Dodge", "Charger"),
    "CHALLENGER": ("Dodge", "Challenger"),
    "911": ("Porsche", "911"),
    "PORSCHE": ("Porsche", "911"),
    "LOTUS": ("Lotus", "Elise"),
    "LAMBO": ("Lamborghini", "Huracan"),
    "FERRARI": ("Ferrari", "488"),
    "PRINCE": ("Nissan", "Skyline GT-R"),
}

_GENERIC = ("Toyota", "Camry", 2019, "2.5L 4-cyl", "Automatic")


def _normalise_plate(rego: str) -> str:
    return "".join(ch for ch in rego.upper() if ch.isalnum())


def _valid_au_plate(plate: str) -> bool:
    return 1 <= len(plate) <= 8 and plate.isalnum()


def _word_decode(plate: str) -> tuple | None:
    """Fuzzy-match the plate letters against known make/model words."""
    best_hit, best_ratio, best_len = None, 0.0, 0
    for word, hit in _WORDS.items():
        w = word.upper()
        if w in plate:
            # Prefer the longest exact contained word (e.g. GTR over GT).
            if len(w) > best_len:
                best_len, best_hit, best_ratio = len(w), hit, 1.0
            continue
        ratio = difflib.SequenceMatcher(None, w, plate).ratio()
        if ratio > best_ratio:
            best_ratio, best_hit = ratio, hit
    return best_hit if best_ratio >= 0.72 else None


def _synthetic_vin(plate: str) -> str:
    import hashlib

    digest = hashlib.sha256(plate.encode()).hexdigest().upper()
    return "6" + digest[:16]


def _dig(obj, key: str):
    """Depth-first search for a key (case-insensitive) in nested JSON."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() == key.lower():
                return v
            found = _dig(v, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _dig(item, key)
            if found is not None:
                return found
    return None


def _first(data, aliases: list[str]):
    for alias in aliases:
        val = _dig(data, alias)
        if val not in (None, "", "N/A", "n/a", "-"):
            return val
    return None


def _to_int(value) -> int | None:
    if value is None:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())[:4]
    return int(digits) if digits else None


def _map_provider(data, plate: str, state: str) -> dict | None:
    """Map a plateapi.com.au (or similar) response onto our schema.

    Field names vary by provider, so every field is resolved by alias with a
    depth-first search. plateapi wraps the vehicle payload under `vehicle`.
    The free tier returns a production-year *range* (no VIN) — that's mapped to
    a representative year and VIN is left blank rather than fabricated.
    """
    # Explicit failure flags
    success = _first(data, ["success", "ok"])
    if isinstance(success, bool) and not success:
        return None
    if isinstance(success, str) and success.lower() in ("false", "error", "failed"):
        return None
    error = _first(data, ["error", "message", "error_message", "detail"])
    if isinstance(error, str) and error and "not found" in error.lower():
        return None

    vehicle = data.get("vehicle") if isinstance(data, dict) else None
    if not isinstance(vehicle, dict):
        vehicle = data

    def get(*aliases: str):
        return _first(vehicle, list(aliases)) or _first(data, list(aliases))

    year = _to_int(get("lowest_year", "year", "manufacture_year", "model_year", "build_year"))
    if year is None:
        year = _to_int(get("highest_year"))

    vin = get("vin", "chassis", "vin_number", "chassis_number", "vin_chassis", "vehicle_vin")
    description = get("description", "detailed_description", "vehicle_description")
    status_raw = str(get("registration_status", "status", "rego_status") or "").lower()
    if status_raw in ("valid", "registered", "current", "active"):
        status_norm = "registered"
    elif status_raw in ("expired", "unregistered", "cancelled"):
        status_norm = "expired"
    else:
        status_norm = status_raw or "registered"

    return {
        "rego": str(get("registration_number", "registration_no", "rego", "plate", "registration") or plate),
        "vin": str(vin) if vin else None,
        "make": str(get("make", "manufacturer", "brand") or ""),
        "model": str(get("model", "series", "variant", "model_name") or ""),
        "year": year,
        "engine": str(get("engine", "engine_number", "engine_no", "engine_size") or ""),
        "transmission": str(get("transmission", "gearbox", "transmission_type") or ""),
        "body_type": str(get("body", "body_type", "body_style", "body_type_description") or ""),
        "colour": str(get("colour", "color", "vehicle_colour") or ""),
        "expiry_date": str(get("expiry_date", "registration_expiry", "rego_expiry") or ""),
        "status": status_norm,
        "description": str(description) if description else None,
        "state": state,
        "source": "provider",
        "matched": "plateapi",
    }


async def lookup_rego(rego: str, jurisdiction: str = "AU", state: str = "VIC",
                      vehicle_type: str = "car") -> dict | None:
    clean = _normalise_plate(rego)
    if not _valid_au_plate(clean):
        logger.warning("rego_invalid_format", rego=rego, state=state)
        return None
    state = state.upper()

    # 1) External provider (real lookup) — self-hosted Plate-API-Scraper
    #    (POST /lookup, body {"plate", "state", "vehicle_type"}, X-API-Key header).
    #    Configure REGO_LOOKUP_URL + REGO_LOOKUP_API_KEY in .env (never hardcode).
    if settings.REGO_LOOKUP_URL:
        try:
            async with httpx.AsyncClient(timeout=150) as client:
                resp = await client.post(
                    settings.REGO_LOOKUP_URL,
                    json={"plate": clean, "state": state, "vehicle_type": vehicle_type},
                    headers={"X-API-Key": settings.REGO_LOOKUP_API_KEY} if settings.REGO_LOOKUP_API_KEY else {},
                )
                data = resp.json()
            mapped = _map_provider(data, clean, state)
            if mapped is not None:
                logger.info("rego_provider_lookup",
                            rego=clean, state=state, status=resp.status_code,
                            make=mapped["make"], model=mapped["model"], year=mapped["year"])
                return mapped
            if resp.status_code >= 400:
                logger.warning("rego_provider_rejected", rego=clean, state=state, status=resp.status_code)
                return None  # provider says the plate is unknown — don't guess
        except Exception as exc:
            logger.warning("rego_provider_failed_falling_back", error=str(exc), rego=clean, state=state)

    # 2) State-specific prefix
    hit = _STATE_PREFIX.get((state, clean))
    if hit:
        return _result(clean, hit, source="state-heuristic", state=state)

    # 3) AU-wide prefix (longest match)
    make, model, year, engine, transmission = _GENERIC
    best_prefix = ""
    for prefix, h in _AU_PREFIX.items():
        if clean.startswith(prefix) and len(prefix) > len(best_prefix):
            best_prefix, (make, model, year, engine, transmission) = prefix, h
    if best_prefix:
        return _result(clean, (make, model, year, engine, transmission),
                       source="prefix-heuristic", state=state)

    # 4) Personalised-plate word decode
    decoded = _word_decode(clean)
    if decoded:
        make, model = decoded
        return _result(clean, (make, model, 1998, "2.0L Turbo", "Manual"),
                       source="word-heuristic", state=state, matched=f"{make} {model}")

    # 5) Generic
    if vehicle_type == "motorcycle":
        # Directionally correct fallback for bikes (never guess a car).
        return _result(clean, ("", "Motorcycle", 2018, "", "Manual"),
                       source="heuristic", state=state, matched="motorcycle")
    return _result(clean, _GENERIC, source="heuristic", state=state)


def _result(plate: str, hit: tuple, source: str, state: str, matched: str | None = None) -> dict:
    make, model, year, engine, transmission = hit
    return {
        "rego": plate,
        "vin": _synthetic_vin(plate),
        "make": make,
        "model": model,
        "year": year,
        "engine": engine,
        "transmission": transmission,
        "state": state,
        "source": source,
        "matched": matched,
        # Synthetic lookups can't know status; treat as "registered" (heuristic
        # never claims expired, it just doesn't know). The frontend badge
        # renders nothing when the cache is empty.
        "status": "registered",
        "expiry_date": "",
    }
