"""Rego (registration plate) lookup.

Uses an optional external provider configured via REGO_LOOKUP_URL. When unset,
returns a deterministic heuristic so the feature works end-to-end offline.
"""

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# make/model heuristics keyed by plate fragment for offline demo mode
_HEURISTIC = {
    ("TOY", "AU"): ("Toyota", "Camry", 2021, "2.5L 4-cyl", "Automatic"),
    ("TOY", "NZ"): ("Toyota", "Corolla", 2020, "1.8L 4-cyl", "CVT"),
    ("HON", "AU"): ("Honda", "Civic", 2022, "1.5L Turbo", "CVT"),
    ("MAZ", "AU"): ("Mazda", "CX-5", 2019, "2.5L 4-cyl", "Automatic"),
    ("FOR", "AU"): ("Ford", "Ranger", 2021, "2.0L Bi-Turbo", "Automatic"),
    ("SUB", "AU"): ("Subaru", "Outback", 2018, "2.5L Boxer", "CVT"),
    ("BMW", "AU"): ("BMW", "3 Series", 2020, "2.0L Turbo", "Automatic"),
    ("AUD", "AU"): ("Audi", "A4", 2019, "2.0L Turbo", "Automatic"),
}


async def lookup_rego(rego: str, jurisdiction: str = "AU") -> dict | None:
    clean = rego.upper().strip().replace(" ", "")
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
            logger.warning("rego_provider_failed", error=str(exc), rego=clean)
            return None

    prefix = clean[:3]
    hit = _HEURISTIC.get((prefix, jurisdiction)) or _HEURISTIC.get((prefix, "AU"))
    if not hit:
        return None
    make, model, year, engine, transmission = hit
    return {
        "rego": clean,
        "vin": f"HEUR{clean:<12}".replace(" ", "0")[:17],
        "make": make,
        "model": model,
        "year": year,
        "engine": engine,
        "transmission": transmission,
        "source": "heuristic",
    }
