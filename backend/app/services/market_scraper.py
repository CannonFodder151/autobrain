"""In-process market-data scrapers (pure HTTP, no browser).
Ported from market-data/ to replace the removed market-data container (AUT-3810).
CarsGuide search + SCA parts-guide taxonomy via plain HTTP. Browser channels
(bikesguide gate, SCA rego resolution) are NOT implemented here — ponytail.
"""

import json
import os
import re

import httpx

CARSGUIDE_SEARCH_URL = os.getenv("CARSGUIDE_SEARCH_URL", "https://www.carsguide.com.au/search")
CARSGUIDE_BASE_URL = os.getenv("CARSGUIDE_BASE_URL", "https://www.carsguide.com.au")
CARSGUIDE_TIMEOUT = float(os.getenv("CARSGUIDE_TIMEOUT", "45"))
CARSGUIDE_MAX_LISTINGS = int(os.getenv("CARSGUIDE_MAX_LISTINGS", "12"))
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

SCA_BASE_URL = os.getenv("SCA_BASE_URL", "https://www.supercheapauto.com.au")
SCA_TIMEOUT = float(os.getenv("SCA_TIMEOUT", "30"))
SCA_MAX_CATEGORIES = int(os.getenv("SCA_MAX_CATEGORIES", "50"))

_NUXT_SCRIPT = re.compile(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', re.S)

_PARTS_CATEGORY_RE = re.compile(
    r'href="(?:https?:)?//[^"]*?/spare-parts/([^"/?]+)[^"]*"'
)

_CATEGORIES_BY_TYPE = {
    "braking": "brakes", "cooling": "cooling", "engine-parts": "engine",
    "fuel-system": "fuel", "clutch-transmission": "transmission",
    "shafts-axles-wheels": "wheels", "suspension": "suspension",
    "steering": "steering", "wipers": "wipers", "aircon-heating": "climate",
    "belts-timing-parts": "belts", "gaskets-seals": "gaskets",
    "body-parts-int-ext": "body", "exhaust-emission": "exhaust",
    "performance-parts": "performance", "manual-transmission": "transmission",
    "manual-transmission-belt-drive": "transmission", "manifolds-downpipes": "exhaust",
    "ignition-coils": "ignition", "ignition-start-charge": "ignition",
    "starter-alternator": "electrical", "lights-bulbs": "lighting",
    "electrical-electronics": "electrical", "audio-accessories": "electrical",
    "tools-garage": "tools", "hp-tools-garden": "tools", "garden-equipment": "tools",
    "marine-parts": "marine", "motorcycle-parts": "motorcycle", "manuals": "manuals",
}

_SERVICE_GROUPS = {
    "brakes": "Brakes", "cooling": "Cooling", "engine": "Engine",
    "fuel": "Fuel System", "transmission": "Transmission", "wheels": "Wheels & Tyres",
    "suspension": "Suspension", "steering": "Steering", "wipers": "Wipers",
    "climate": "Climate", "belts": "Belts & Timing", "gaskets": "Gaskets & Seals",
    "body": "Body", "exhaust": "Exhaust", "performance": "Performance",
    "ignition": "Ignition", "electrical": "Electrical", "lighting": "Lighting",
    "tools": "Tools", "marine": "Marine", "motorcycle": "Motorcycle", "manuals": "Manuals",
}


def _resolve(arr, i):
    if not isinstance(i, int):
        return i
    v = arr[i]
    if isinstance(v, int):
        return v
    if isinstance(v, list):
        return [_resolve(arr, x) for x in v]
    if isinstance(v, dict):
        return {k: _resolve(arr, val) if isinstance(val, int) else val for k, val in v.items()}
    return v


def _parse_nuxt_listings(html: str) -> list[dict]:
    m = _NUXT_SCRIPT.search(html)
    if not m:
        return []
    arr = json.loads(m.group(1))
    root = _resolve(arr, 1)
    listings = []
    data = root.get("data") if isinstance(root, dict) else None
    if not isinstance(data, list):
        return []
    for item in data:
        if not isinstance(item, dict):
            continue
        for key, value in item.items():
            if "siteWideSearch" not in key:
                continue
            mp = (value or {}).get("data", {}).get("marketplace", {})
            if not isinstance(mp, dict):
                continue
            for idx in mp.get("data") or []:
                raw = _resolve(arr, idx)
                if isinstance(raw, dict) and "_source" in raw:
                    raw = raw["_source"]
                if isinstance(raw, dict):
                    listings.append(raw)
    return listings


def _to_float(value) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if value is None:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit() or ch == ".")
    try:
        return float(digits) if digits else None
    except ValueError:
        return None


def _to_int(value) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if value is None:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return int(digits) if digits else None


def _map_listing(raw: dict) -> dict | None:
    price = raw.get("price")
    if isinstance(price, dict):
        price = price.get("advertised_price")
    title_parts = []
    year = _to_int(raw.get("manu_year"))
    if year:
        title_parts.append(str(year))
    title_parts.extend(p for p in (raw.get("make"), raw.get("model"), raw.get("variant")) if p)
    title = " ".join(p.strip() for p in title_parts if str(p).strip()) or ""
    url = raw.get("url") or raw.get("url_cg") or ""
    if url and url.startswith("/"):
        url = CARSGUIDE_BASE_URL + url
    elif url and not url.startswith("http"):
        url = CARSGUIDE_BASE_URL + "/" + url
    return {
        "title": title,
        "price": _to_float(price),
        "year": year,
        "odometer_km": _to_int(raw.get("odometer")),
        "source": "carsguide",
        "url": url,
    }


def _filter_year(listings: list[dict], year: int | None) -> list[dict]:
    if not year:
        return listings
    exact = [l for l in listings if l["year"] == year]
    if len(exact) >= 3:
        return exact
    nearby = [l for l in listings if l["year"] and abs(l["year"] - year) <= 1]
    if len(nearby) >= 3:
        return nearby
    return listings


async def search_carsguide(query: str, year: int | None = None) -> dict:
    params = {"query": query}
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en-AU,en;q=0.9"}
    async with httpx.AsyncClient(timeout=CARSGUIDE_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(CARSGUIDE_SEARCH_URL, params=params, headers=headers)
        resp.raise_for_status()
        html = resp.text
    raw_listings = _parse_nuxt_listings(html)
    listings = []
    for raw in raw_listings:
        listing = _map_listing(raw)
        if listing and listing["price"]:
            listings.append(listing)
    listings = _filter_year(listings, year)
    return {"source": "carsguide", "listings": listings[:CARSGUIDE_MAX_LISTINGS]}


def _parse_categories(html: str) -> list[dict]:
    categories = []
    seen = set()
    for match in _PARTS_CATEGORY_RE.finditer(html):
        slug = match.group(1)
        if slug in seen or slug in ("spare-parts", "vehicle", "parts-guide"):
            continue
        seen.add(slug)
        if len(categories) >= SCA_MAX_CATEGORIES:
            break
        name = slug.replace("-", " ").replace("_", " ").title()
        part_category = _CATEGORIES_BY_TYPE.get(slug, "other")
        service_group = _SERVICE_GROUPS.get(part_category, "Other")
        categories.append({
            "slug": slug,
            "name": name,
            "service_group": service_group,
            "part_category": part_category,
            "url": f"{SCA_BASE_URL}/spare-parts/{slug}",
        })
    return categories


async def fetch_sca_categories() -> list[dict]:
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en-AU,en;q=0.9"}
    async with httpx.AsyncClient(timeout=SCA_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(f"{SCA_BASE_URL}/parts-guide", headers=headers)
        resp.raise_for_status()
        html = resp.text
    return _parse_categories(html)


async def fetch_sca_parts(
    rego: str | None = None,
    state: str | None = None,
    make: str = "",
    model: str = "",
    year: int | None = None,
    vehicle_type: str = "car",
) -> dict:
    """SCA parts-guide lookup: returns {source, vehicle, categories, note, listings}.
    Browser channel (rego resolution via Playwright) is NOT implemented — ponytail.
    """
    vehicle = None
    if make or model or year:
        vehicle = {
            "make": make or "Unknown",
            "model": model or "Unknown",
            "year": year,
            "rego": rego,
            "state": state.upper() if state else None,
        }
    try:
        categories = await fetch_sca_categories()
    except Exception as exc:
        return {
            "source": "supercheap",
            "vehicle": vehicle,
            "categories": [],
            "note": f"network error: {exc.__class__.__name__}",
            "listings": [],
        }
    if not categories:
        return {
            "source": "supercheap",
            "vehicle": vehicle,
            "categories": [],
            "note": "no categories found on SCA parts-guide",
            "listings": [],
        }
    note = None
    if rego and not vehicle:
        note = "vehicle resolved via browser (rego + state) — browser channel not implemented"
    return {
        "source": "supercheap",
        "vehicle": vehicle,
        "categories": categories,
        "note": note,
        "listings": [],
    }