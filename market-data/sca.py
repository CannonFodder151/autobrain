"""Supercheap Auto parts-guide scraper: vehicle fitment and catalog categories.

SCA is a Salesforce Commerce Cloud site. The parts-guide page is SSR-rendered
and the category taxonomy is embedded in the main HTML menu. Vehicle-specific
fitment requires browser interaction (rego lookup via FindRegoVehicle).

Pattern: plain HTTP first (deterministic, fast), then browser (Playwright) for
rego-to-vehicle resolution. Falls back gracefully when both fail.

ponytail: full vehicle-fit parts extraction across the SCA catalog would need
undetected-chromedriver; added to browser.py if needed.
"""

import asyncio
import json
import os
import re
import subprocess
import sys

import httpx

BASE_URL = os.getenv("SCA_BASE_URL", "https://www.supercheapauto.com.au")
REQUEST_TIMEOUT = float(os.getenv("SCA_TIMEOUT", "30"))
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
MAX_CATEGORIES = int(os.getenv("SCA_MAX_CATEGORIES", "50"))

_PARTS_CATEGORY_RE = re.compile(
    r'href="(?:https?:)?//[^"]*?/spare-parts/([^"/?]+)[^"]*'
)

# SCA parts-guide category slug -> internal normalised part category.
_CATEGORIES_BY_TYPE = {
    "braking": "brakes",
    "cooling": "cooling",
    "engine-parts": "engine",
    "fuel-system": "fuel",
    "clutch-transmission": "transmission",
    "shafts-axles-wheels": "wheels",
    "suspension": "suspension",
    "steering": "steering",
    "wipers": "wipers",
    "aircon-heating": "climate",
    "belts-timing-parts": "belts",
    "gaskets-seals": "gaskets",
    "body-parts-int-ext": "body",
    "exhaust-emission": "exhaust",
    "performance-parts": "performance",
    "manual-transmission": "transmission",
    "manual-transmission-belt-drive": "transmission",
    "manifolds-downpipes": "exhaust",
    "ignition-coils": "ignition",
    "ignition-start-charge": "ignition",
    "starter-alternator": "electrical",
    "lights-bulbs": "lighting",
    "electrical-electronics": "electrical",
    "audio-accessories": "electrical",
    "tools-garage": "tools",
    "hp-tools-garden": "tools",
    "garden-equipment": "tools",
    "marine-parts": "marine",
    "motorcycle-parts": "motorcycle",
    "manuals": "manuals",
}

# Internal normalised part category -> human service group label.
_SERVICE_GROUPS = {
    "brakes": "Brakes",
    "cooling": "Cooling",
    "engine": "Engine",
    "fuel": "Fuel System",
    "transmission": "Transmission",
    "wheels": "Wheels & Tyres",
    "suspension": "Suspension",
    "steering": "Steering",
    "wipers": "Wipers",
    "climate": "Climate",
    "belts": "Belts & Timing",
    "gaskets": "Gaskets & Seals",
    "body": "Body",
    "exhaust": "Exhaust",
    "performance": "Performance",
    "ignition": "Ignition",
    "electrical": "Electrical",
    "lighting": "Lighting",
    "tools": "Tools",
    "marine": "Marine",
    "motorcycle": "Motorcycle",
    "manuals": "Manuals",
}


def _empty(note: str) -> dict:
    return {"source": "supercheap", "vehicle": None, "categories": [], "note": note}


async def _browser_search(rego: str, state: str) -> dict | None:
    """Run the Playwright worker in a subprocess for rego->vehicle + categories."""
    cmd = [
        sys.executable,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "browser.py"),
        "sca",
        rego,
        state,
    ]
    try:
        cp = await asyncio.to_thread(
            subprocess.run,
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=100,
        )
    except subprocess.TimeoutExpired:
        return _empty("gated: SCA browser channel timed out")
    stdout = (cp.stdout or "").strip()
    try:
        data = json.loads(stdout.splitlines()[-1])
    except Exception:
        return _empty("gated: SCA browser worker failed")
    if data.get("ok"):
        return data
    note = data.get("note") or f"gated: SCA ({data.get('kind')})"
    return _empty(note)


def _parse_categories(html: str) -> list[dict]:
    """Extract parts categories from the SCA parts-guide menu.

    Returns a list of {slug, name, service_group, part_category} dicts.
    Pure function – fully testable with sample HTML.
    """
    categories = []
    seen = set()
    for match in _PARTS_CATEGORY_RE.finditer(html):
        slug = match.group(1)
        if slug in seen or slug in ("spare-parts", "vehicle", "parts-guide"):
            continue
        seen.add(slug)
        if len(categories) >= MAX_CATEGORIES:
            break

        name = slug.replace("-", " ").replace("_", " ").title()
        part_category = _CATEGORIES_BY_TYPE.get(slug, "other")
        service_group = _SERVICE_GROUPS.get(part_category, "Other")

        categories.append({
            "slug": slug,
            "name": name,
            "service_group": service_group,
            "part_category": part_category,
            "url": f"{BASE_URL}/spare-parts/{slug}",
        })
    return categories


def _extract_vehicle_from_rego(html: str) -> dict | None:
    """Parse vehicle data from SCA FindRegoVehicle response."""
    if not html or "vehicle" not in html.lower():
        return None
    try:
        data = json.loads(html)
        vehicle = data.get("vehicle", data)
        if isinstance(vehicle, dict):
            return {
                "make": vehicle.get("make"),
                "model": vehicle.get("model"),
                "year": vehicle.get("year") or vehicle.get("manufacture_year"),
                "colour": vehicle.get("colour"),
            }
    except json.JSONDecodeError:
        pass
    return None


async def search_sca(
    rego: str | None = None,
    state: str | None = None,
    make: str = "",
    model: str = "",
    year: int | None = None,
    vehicle_type: str = "car",
) -> dict:
    """SCA parts-guide search.

    Returns {source: "supercheap", vehicle: {...}, categories: [...], listings: []}.
    If rego+state provided, attempts browser-based vehicle resolution.
    Otherwise falls back to the parts-guide category taxonomy via plain HTTP.
    """
    if rego and state:
        result = await _browser_search(rego, state.upper())
        if result is not None:
            return result

    try:
        headers = {"User-Agent": USER_AGENT, "Accept-Language": "en-AU,en;q=0.9"}
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(f"{BASE_URL}/parts-guide", headers=headers)
            resp.raise_for_status()
            html = resp.text
    except httpx.HTTPError as exc:
        return _empty(f"network error: {exc.__class__.__name__}")

    categories = _parse_categories(html)
    vehicle = None
    if make or model or year:
        vehicle = {
            "make": make or "Unknown",
            "model": model or "Unknown",
            "year": year,
            "variant": None,
        }

    if not categories:
        return _empty("no categories found on SCA parts-guide")

    note = None
    if rego and not vehicle:
        note = "vehicle resolved via browser (rego + state)"
    return {
        "source": "supercheap",
        "vehicle": vehicle,
        "categories": categories,
        "note": note,
        "listings": [],
    }