"""Market-data scraper: CarsGuide, BikesGuide, and SCA parts-guide.

Merged from the standalone market-data service (AUT-5868). The backend now
runs the scraping logic directly instead of calling an external HTTP API.

Primary scrape source is CarsGuide's SSR search page (Nuxt __NUXT_DATA__),
which works over plain HTTP without a browser. BikesGuide and SCA use
Playwright/Chromium as a fallback for gated pages.
"""

import asyncio
import json
import os
import re
import subprocess
import sys

import httpx

SEARCH_URL = os.getenv("CARSGUIDE_SEARCH_URL", "https://www.carsguide.com.au/search")
BASE_URL = os.getenv("CARSGUIDE_BASE_URL", "https://www.carsguide.com.au")
REQUEST_TIMEOUT = float(os.getenv("CARSGUIDE_TIMEOUT", "45"))
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
MAX_LISTINGS = int(os.getenv("CARSGUIDE_MAX_LISTINGS", "12"))

BIKEGUIDE_SEARCH_URL = os.getenv("BIKEGUIDE_SEARCH_URL", "https://www.bikesguide.com.au/search")
BIKEGUIDE_TIMEOUT = float(os.getenv("BIKEGUIDE_TIMEOUT", "45"))
BIKEGUIDE_MAX_LISTINGS = int(os.getenv("BIKEGUIDE_MAX_LISTINGS", "12"))
BROWSER_ENABLED = os.getenv("BIKEGUIDE_BROWSER", "1").lower() in ("1", "true", "yes")

SCA_BASE_URL = os.getenv("SCA_BASE_URL", "https://www.supercheapauto.com.au")
SCA_TIMEOUT = float(os.getenv("SCA_TIMEOUT", "30"))
SCA_MAX_CATEGORIES = int(os.getenv("SCA_MAX_CATEGORIES", "50"))

_NUXT_SCRIPT = re.compile(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', re.S)
_PARTS_CATEGORY_RE = re.compile(
    r'href="(?:https?:)?//[^"]*?/spare-parts/([^"/?]+)[^"]*'
)

_PARKED_MARKS = ("domain may be for sale", "may be for sale", "abovedomains")
_GATE_MARKS = ("fingerprint", "tr_uuid")

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


def _resolve(arr, i):
    """Resolve one __NUXT_DATA__ array entry (indices reference earlier entries)."""
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


def _to_float(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if value is None:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit() or ch == ".")
    try:
        return float(digits) if digits else None
    except ValueError:
        return None


def _to_int(value):
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
        url = BASE_URL + url
    elif url and not url.startswith("http"):
        url = BASE_URL + "/" + url
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
    """Search CarsGuide for used-car listings."""
    params = {"query": query}
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en-AU,en;q=0.9"}
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(SEARCH_URL, params=params, headers=headers)
        resp.raise_for_status()
        html = resp.text
    raw_listings = _parse_nuxt_listings(html)
    listings = []
    for raw in raw_listings:
        listing = _map_listing(raw)
        if listing and listing["price"]:
            listings.append(listing)
    listings = _filter_year(listings, year)
    return {"source": "carsguide", "listings": listings[:MAX_LISTINGS]}


def _gated(html: str) -> bool:
    if _NUXT_SCRIPT.search(html):
        return False
    return "fingerprint" in html.lower() or "tr_uuid" in html


def _parked(html: str) -> bool:
    return any(m in html.lower() for m in _PARKED_MARKS)


def _empty(note: str) -> dict:
    return {"source": "bikesguide", "listings": [], "note": note}


async def _browser_search(query: str, year: int | None) -> dict | None:
    """Run the Playwright worker in a subprocess."""
    cmd = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "market_data_browser.py"),
           "bikesguide", query, str(year or "")]
    try:
        cp = await asyncio.to_thread(
            subprocess.run, cmd, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, timeout=100)
    except subprocess.TimeoutExpired:
        return _empty("gated: bikesguide browser channel timed out")
    stdout = (cp.stdout or "").strip()
    try:
        data = json.loads(stdout.splitlines()[-1])
    except Exception:
        return _empty("gated: bikesguide browser worker failed")
    if data.get("ok"):
        return {"source": "bikesguide", "listings": data.get("listings", [])}
    note = data.get("note") or f"gated: bikesguide ({data.get('kind')})"
    return _empty(note)


async def search_bikesguide(query: str, year: int | None = None) -> dict:
    """Search BikesGuide for used-motorcycle listings."""
    params = {"query": query}
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en-AU,en;q=0.9"}
    try:
        async with httpx.AsyncClient(timeout=BIKEGUIDE_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(BIKEGUIDE_SEARCH_URL, params=params, headers=headers)
            resp.raise_for_status()
            html = resp.text
    except httpx.HTTPError as exc:
        return _empty(f"gated: bikesguide request failed ({exc.__class__.__name__})")

    if _parked(html):
        return _empty("parked: bikesguide.com.au domain is parked (for sale); no listings exist")
    if _gated(html):
        if BROWSER_ENABLED:
            return await _browser_search(query, year)
        return _empty("gated: bikesguide requires a browser channel (FingerprintJS)")

    listings = []
    for raw in _parse_nuxt_listings(html):
        listing = _map_listing(raw)
        if listing and listing["price"]:
            listings.append(listing)
    listings = _filter_year(listings, year)
    return {"source": "bikesguide", "listings": listings[:BIKEGUIDE_MAX_LISTINGS]}


def _parse_categories(html: str) -> list[dict]:
    """Extract parts categories from the SCA parts-guide menu."""
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


async def _browser_search_sca(rego: str, state: str) -> dict | None:
    """Run the Playwright worker in a subprocess for rego->vehicle + categories."""
    cmd = [
        sys.executable,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "market_data_browser.py"),
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


async def search_sca(
    rego: str | None = None,
    state: str | None = None,
    make: str = "",
    model: str = "",
    year: int | None = None,
    vehicle_type: str = "car",
) -> dict:
    """SCA parts-guide search."""
    if rego and state:
        result = await _browser_search_sca(rego, state.upper())
        if result and result.get("ok"):
            return result

    try:
        headers = {"User-Agent": USER_AGENT, "Accept-Language": "en-AU,en;q=0.9"}
        async with httpx.AsyncClient(timeout=SCA_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(f"{SCA_BASE_URL}/parts-guide", headers=headers)
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
