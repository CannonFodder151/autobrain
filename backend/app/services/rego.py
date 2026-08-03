"""Rego (Australian registration plate) lookup.

Primary path: an external provider configured via REGO_LOOKUP_URL + REGO_LOOKUP_API_KEY
(a real AU rego-check service). When unset or on failure, returns a deterministic
heuristic so the feature works end-to-end offline — it never 404s on a valid
Australian plate format.

Australian plates: 1–8 alphanumeric characters, letters and digits only
(e.g. "ABC123", "1ABC234", "NSW 01AA"), case/spacing-insensitive.
"""

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Common Australian make/model heuristics keyed by plate prefix fragment.
# (prefix, jurisdiction) -> (make, model, year, engine, transmission)
_HEURISTIC: dict[tuple[str, str], tuple] = {
    ("TOY", "AU"): ("Toyota", "Camry", 2021, "2.5L 4-cyl", "Automatic"),
    ("COR", "AU"): ("Toyota", "Corolla", 2020, "1.8L 4-cyl", "CVT"),
    ("HIL", "AU"): ("Toyota", "HiLux", 2021, "2.8L Turbo Diesel", "Automatic"),
    ("RAV", "AU"): ("Toyota", "RAV4", 2022, "2.5L Hybrid", "CVT"),
    ("KLU", "AU"): ("Toyota", "Kluger", 2020, "3.5L V6", "Automatic"),
    ("LAN", "AU"): ("Toyota", "LandCruiser", 2019, "4.5L Turbo Diesel", "Automatic"),
    ("HON", "AU"): ("Honda", "Civic", 2022, "1.5L Turbo", "CVT"),
    ("ACC", "AU"): ("Honda", "Accord", 2019, "2.0L Turbo", "Automatic"),
    ("HRV", "AU"): ("Honda", "HR-V", 2021, "1.8L 4-cyl", "CVT"),
    ("MAZ", "AU"): ("Mazda", "CX-5", 2019, "2.5L 4-cyl", "Automatic"),
    ("MZD", "AU"): ("Mazda", "Mazda3", 2021, "2.0L 4-cyl", "Automatic"),
    ("FOR", "AU"): ("Ford", "Ranger", 2021, "2.0L Bi-Turbo", "Automatic"),
    ("FOC", "AU"): ("Ford", "Focus", 2019, "1.5L Turbo", "Automatic"),
    ("MUS", "AU"): ("Ford", "Mustang", 2022, "5.0L V8", "Automatic"),
    ("HOL", "AU"): ("Holden", "Commodore", 2019, "3.6L V6", "Automatic"),
    ("SUB", "AU"): ("Subaru", "Outback", 2018, "2.5L Boxer", "CVT"),
    ("FOR", "NZ"): ("Subaru", "Forester", 2020, "2.5L Boxer", "CVT"),
    ("WRX", "AU"): ("Subaru", "WRX", 2021, "2.0L Turbo", "Manual"),
    ("BMW", "AU"): ("BMW", "3 Series", 2020, "2.0L Turbo", "Automatic"),
    ("X3", "AU"): ("BMW", "X3", 2021, "2.0L Turbo", "Automatic"),
    ("AUD", "AU"): ("Audi", "A4", 2019, "2.0L Turbo", "Automatic"),
    ("Q5", "AU"): ("Audi", "Q5", 2020, "2.0L Turbo", "Automatic"),
    ("MER", "AU"): ("Mercedes-Benz", "C-Class", 2020, "2.0L Turbo", "Automatic"),
    ("GL", "AU"): ("Mercedes-Benz", "GLC", 2021, "2.0L Turbo", "Automatic"),
    ("NIS", "AU"): ("Nissan", "X-Trail", 2020, "2.5L 4-cyl", "CVT"),
    ("NAV", "AU"): ("Nissan", "Navara", 2019, "2.3L Turbo Diesel", "Automatic"),
    ("HYU", "AU"): ("Hyundai", "i30", 2021, "2.0L 4-cyl", "Automatic"),
    ("TU", "AU"): ("Hyundai", "Tucson", 2020, "2.0L 4-cyl", "Automatic"),
    ("KIA", "AU"): ("Kia", "Sportage", 2021, "2.0L 4-cyl", "Automatic"),
    ("VW", "AU"): ("Volkswagen", "Golf", 2020, "1.4L Turbo", "DSG"),
    ("VW", "NZ"): ("Volkswagen", "Tiguan", 2021, "2.0L Turbo", "DSG"),
    ("MIT", "AU"): ("Mitsubishi", "Triton", 2020, "2.4L Turbo Diesel", "Automatic"),
    ("OUT", "AU"): ("Mitsubishi", "Outlander", 2019, "2.4L 4-cyl", "CVT"),
    ("ISU", "AU"): ("Isuzu", "D-Max", 2021, "3.0L Turbo Diesel", "Automatic"),
    ("RAM", "AU"): ("Ram", "1500", 2022, "5.7L HEMI V8", "Automatic"),
    ("JEE", "AU"): ("Jeep", "Grand Cherokee", 2020, "3.6L V6", "Automatic"),
}

_GENERIC = ("Toyota", "Camry", 2019, "2.5L 4-cyl", "Automatic")


def _normalise_plate(rego: str) -> str:
    return "".join(ch for ch in rego.upper() if ch.isalnum())


def _valid_au_plate(plate: str) -> bool:
    return 1 <= len(plate) <= 8 and plate.isalnum()


async def lookup_rego(rego: str, jurisdiction: str = "AU") -> dict | None:
    clean = _normalise_plate(rego)
    if not _valid_au_plate(clean):
        logger.warning("rego_invalid_format", rego=rego)
        return None

    # 1) External provider (real lookup) if configured
    if settings.REGO_LOOKUP_URL:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    settings.REGO_LOOKUP_URL,
                    params={"rego": clean, "jurisdiction": jurisdiction},
                    headers={"X-Api-Key": settings.REGO_LOOKUP_API_KEY} if settings.REGO_LOOKUP_API_KEY else {},
                )
                resp.raise_for_status()
                data = resp.json()
                data["source"] = "provider"
                return data
        except Exception as exc:
            logger.warning("rego_provider_failed_falling_back", error=str(exc), rego=clean)

    # 2) Heuristic — match the longest prefix in the database
    make, model, year, engine, transmission = _GENERIC
    best_prefix = ""
    for (prefix, jur), hit in _HEURISTIC.items():
        if jur == jurisdiction and clean.startswith(prefix) and len(prefix) > len(best_prefix):
            best_prefix = prefix
            make, model, year, engine, transmission = hit

    vin = _synthetic_vin(clean)
    return {
        "rego": clean,
        "vin": vin,
        "make": make,
        "model": model,
        "year": year,
        "engine": engine,
        "transmission": transmission,
        "source": "heuristic",
        "matched_prefix": best_prefix or None,
    }


def _synthetic_vin(plate: str) -> str:
    """Deterministic 17-char VIN derived from the plate (offline demo mode only)."""
    import hashlib

    digest = hashlib.sha256(plate.encode()).hexdigest().upper()
    vin = "6" + digest[:16]
    return vin
