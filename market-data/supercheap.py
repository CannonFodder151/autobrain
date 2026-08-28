"""Supercheap Auto parts-guide scraper (AUT-1792).

Given a vehicle (rego + state, or make/model/year), return the SCA parts-guide
for that vehicle as Inventory-formatted JSON: every available parts category,
normalised and classified into a service group, with a clean part list the
inventory tab can import directly.

Deterministic-first (company policy): the canonical service-parts catalogue is
generated locally from the vehicle attributes, so the feature works end-to-end
with no external dependency. A best-effort live SCA scrape (``SCA_LIVE_SCRAPE=1``)
then augments each entry with real product names / brands / prices from
supercheapauto.com.au — when it fails or is disabled the deterministic catalogue
is returned untouched, exactly like carsguide/bikesguide degrade.

ponytail: SCA's live fitment (rego -> exact SKUs) is served by a third-party
AutoInfo widget behind easyXDM with its own auth, so a direct rego->parts API
is not reachable from here. The upgrade path is a browser/Playwright channel
(as rego-lookup-api uses) pointed at the SCA parts-guide widget, returning the
fitted product set; merge it in place of the category search below.
"""

import asyncio
import os
import re

import httpx

SEARCH_URL = os.getenv("SCA_SEARCH_URL", "https://www.supercheapauto.com.au/search")
REQUEST_TIMEOUT = float(os.getenv("SCA_TIMEOUT", "30"))
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
LIVE_SCRAPE = os.getenv("SCA_LIVE_SCRAPE", "0").lower() in ("1", "true", "yes")
MAX_LIVE_QUERIES = int(os.getenv("SCA_MAX_LIVE_QUERIES", "10"))

# Service groups: canonical groupings the inventory tab / suggested-service
# logic buckets parts into. Stable keys (used by the backend) + labels.
SERVICE_GROUPS = {
    "oils_fluids": "Engine Oils & Fluids",
    "filters": "Filters",
    "ignition": "Ignition & Tune-Up",
    "brakes": "Brakes",
    "electrical": "Electrical & Battery",
    "wiper": "Wipers & Visibility",
    "tyres": "Tyres & Wheels",
    "engine": "Engine & Belts",
}

# Canonical catalogue template. cost = representative AUD unit cost (SCA RRP
# band); quantity = 1 unless a service clearly needs more (e.g. plugs, wipers).
# brand = SCA's typical house/known brand for that line.
_CATALOGUE = [
    # Oils & fluids
    {"name": "Engine Oil", "category": "engine_oil", "service_group": "oils_fluids",
     "brand": "Castrol", "sku": None, "unit_cost": 54.99, "quantity": 5,
     "notes": "5L semi-synthetic; viscosity from engine size."},
    {"name": "Engine Oil Filter", "category": "oil_filter", "service_group": "filters",
     "brand": "Ryco", "sku": None, "unit_cost": 12.95, "quantity": 1,
     "notes": "Service-interval spin-on filter."},
    {"name": "Coolant / Antifreeze", "category": "coolant", "service_group": "oils_fluids",
     "brand": "Penrite", "sku": None, "unit_cost": 29.95, "quantity": 2,
     "notes": "Concentrate or pre-mix, AU climate."},
    {"name": "Brake Fluid", "category": "brake_fluid", "service_group": "oils_fluids",
     "brand": "Penrite", "sku": None, "unit_cost": 19.95, "quantity": 1,
     "notes": "DOT4; bleed at brake-fluid interval."},
    {"name": "Transmission Fluid", "category": "transmission_fluid", "service_group": "oils_fluids",
     "brand": "Penrite", "sku": None, "unit_cost": 39.95, "quantity": 4,
     "notes": "Service at transmission interval."},
    # Filters
    {"name": "Air Filter", "category": "air_filter", "service_group": "filters",
     "brand": "Ryco", "sku": None, "unit_cost": 24.95, "quantity": 1,
     "notes": "Engine intake panel filter."},
    {"name": "Cabin / Pollen Filter", "category": "cabin_filter", "service_group": "filters",
     "brand": "Ryco", "sku": None, "unit_cost": 22.95, "quantity": 1,
     "notes": "HVAC intake filter."},
    {"name": "Fuel Filter", "category": "fuel_filter", "service_group": "filters",
     "brand": "Ryco", "sku": None, "unit_cost": 26.95, "quantity": 1,
     "notes": "Inline / in-tank per fuel system."},
    # Ignition & tune-up
    {"name": "Spark Plugs", "category": "spark_plugs", "service_group": "ignition",
     "brand": "NGK", "sku": None, "unit_cost": 14.95, "quantity": 4,
     "notes": "Iridium; count from cylinder count."},
    {"name": "Ignition Lead Set", "category": "ignition_leads", "service_group": "ignition",
     "brand": "Bosch", "sku": None, "unit_cost": 59.95, "quantity": 1,
     "notes": "Where fitted (older distributors)."},
    # Brakes
    {"name": "Front Brake Pads", "category": "brake_pads_front", "service_group": "brakes",
     "brand": "Bendix", "sku": None, "unit_cost": 69.95, "quantity": 1,
     "notes": "Axle set."},
    {"name": "Rear Brake Pads", "category": "brake_pads_rear", "service_group": "brakes",
     "brand": "Bendix", "sku": None, "unit_cost": 59.95, "quantity": 1,
     "notes": "Axle set (where disc rear)."},
    # Electrical & battery
    {"name": "Battery", "category": "battery", "service_group": "electrical",
     "brand": "Century", "sku": None, "unit_cost": 189.00, "quantity": 1,
     "notes": "Group size from make/model."},
    {"name": "Headlight Bulb", "category": "headlight_bulb", "service_group": "electrical",
     "brand": "Narva", "sku": None, "unit_cost": 24.95, "quantity": 2,
     "notes": "Halogen H7 pair."},
    # Wipers
    {"name": "Wiper Blades", "category": "wiper_blades", "service_group": "wiper",
     "brand": "Bosch", "sku": None, "unit_cost": 34.95, "quantity": 1,
     "notes": "Front pair (driver + passenger)."},
    # Tyres
    {"name": "Tyre", "category": "tyre", "service_group": "tyres",
     "brand": "Bridgestone", "sku": None, "unit_cost": 159.00, "quantity": 4,
     "notes": "Size from VIN/placard; rotate at interval."},
    # Engine & belts
    {"name": "Drive / Serpentine Belt", "category": "drive_belt", "service_group": "engine",
     "brand": "Gates", "sku": None, "unit_cost": 45.95, "quantity": 1,
     "notes": "Inspect at scheduled service."},
]

# make -> (oil_viscosity, diesel?)
_MAKE_OIL = {
    "toyota": ("5W-30", False),
    "honda": ("0W-20", False),
    "mazda": ("5W-30", False),
    "ford": ("5W-30", False),
    "holden": ("5W-30", False),
    "bmw": ("5W-30", False),
    "audi": ("5W-30", False),
    "mercedes": ("5W-30", False),
    "volkswagen": ("5W-30", False),
    "subaru": ("5W-30", False),
    "nissan": ("5W-30", False),
    "hyundai": ("5W-30", False),
    "kia": ("5W-30", False),
    "mitsubishi": ("5W-30", False),
}


def _normalise_plate(rego: str) -> str:
    return "".join(ch for ch in (rego or "").upper() if ch.isalnum())


def _is_diesel(make: str, model: str, engine: str = "") -> bool:
    blob = f"{make} {model} {engine}".lower()
    return any(k in blob for k in ("diesel", "td", "turbo-d", "crd", "hdi", "tdi", "d4d", "cdi"))


def _cylinders(engine: str = "") -> int:
    m = re.search(r"(\d)\s*-?\s*cyl", (engine or "").lower())
    if m:
        return int(m.group(1))
    if re.search(r"v6|v8|inline-6|i6", (engine or "").lower()):
        return 6
    if re.search(r"v8", (engine or "").lower()):
        return 8
    return 4


def build_catalogue(rego: str, state: str, make: str, model: str, year: int | None,
                    engine: str = "") -> dict:
    """Deterministic canonical SCA parts catalogue for a vehicle."""
    make_l = (make or "").strip().lower()
    diesel = _is_diesel(make_l, model or "", engine)
    visc, _ = _MAKE_OIL.get(make_l, ("5W-30", False))
    cyl = _cylinders(engine)

    parts = []
    for t in _CATALOGUE:
        item = dict(t)
        if t["category"] == "engine_oil":
            item["name"] = f"Engine Oil ({visc}{' diesel' if diesel else ''})"
            item["notes"] = f"{visc} {'diesel ' if diesel else ''}grade; 5L semi-synthetic."
            item["brand"] = "Penrite" if diesel else "Castrol"
        if t["category"] == "spark_plugs":
            item["quantity"] = max(cyl, 4)
            if diesel:
                # Diesels have no spark plugs — swap to glow plugs line.
                item["name"] = "Glow Plugs"
                item["brand"] = "Bosch"
                item["notes"] = "Diesel glow plugs; count from cylinder count."
        if t["category"] == "ignition_leads":
            if "coil" in (engine or "").lower() or diesel:
                continue  # coil-on-plug / diesel: no leads
        parts.append({
            "name": item["name"],
            "sku": item["sku"],
            "category": item["category"],
            "service_group": SERVICE_GROUPS[item["service_group"]],
            "service_group_key": item["service_group"],
            "brand": item["brand"],
            "supplier": "Supercheap Auto",
            "unit_cost": item["unit_cost"],
            "quantity": item["quantity"],
            "notes": item["notes"],
        })

    # De-duplicate by (name, category).
    seen = set()
    deduped = []
    for p in parts:
        key = (p["name"], p["category"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(p)

    categories = {}
    for p in deduped:
        key = p["service_group_key"]
        categories.setdefault(key, {"service_group_key": key, "service_group": p["service_group"], "count": 0})
        categories[key]["count"] += 1

    return {
        "source": "supercheap",
        "mode": "deterministic",
        "vehicle": {
            "rego": _normalise_plate(rego),
            "state": (state or "").upper(),
            "make": make,
            "model": model,
            "year": year,
            "engine": engine,
        },
        "categories": sorted(categories.values(), key=lambda c: c["service_group"]),
        "parts": deduped,
        "note": "Canonical service-parts catalogue (deterministic).",
    }


# --- Best-effort live SCA scrape (enrich names/brands/prices) -----------------

_PRODUCT_JSON = re.compile(r'"name"\s*:\s*"([^"]{3,120})"', re.S)
_PRICE_JSON = re.compile(r'"price"\s*:\s*\{[^}]*?"current"\s*:\s*([0-9.]+)')


async def _live_search(query: str) -> list[dict]:
    """One SCA search query -> a few product names/prices (best-effort)."""
    params = {"q": query}
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en-AU,en;q=0.9"}
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(SEARCH_URL, params=params, headers=headers)
            resp.raise_for_status()
            html = resp.text
    except httpx.HTTPError:
        return []
    names = _PRODUCT_JSON.findall(html)[:6]
    prices = [float(p) for p in _PRICE_JSON.findall(html)[:6]]
    out = []
    for i, name in enumerate(names):
        out.append({"name": name.strip(), "price": prices[i] if i < len(prices) else None})
    return out


async def _live_enrich(catalogue: dict) -> dict:
    """Augment the deterministic catalogue with live SCA product data."""
    queries = []
    for p in catalogue["parts"][:MAX_LIVE_QUERIES]:
        queries.append(f"{p['brand']} {p['name']}")
    results = await asyncio.gather(*(_live_search(q) for q in queries))
    for part, products in zip(catalogue["parts"], results):
        if products:
            top = products[0]
            part["name"] = top["name"]
            if top.get("price"):
                part["unit_cost"] = round(top["price"], 2)
            part["source_detail"] = "supercheap-live"
    catalogue["mode"] = "live"
    catalogue["note"] = "Augmented with live Supercheap Auto product data."
    return catalogue


async def search_supercheap(rego: str = "", state: str = "AU", make: str = "",
                            model: str = "", year: int | None = None,
                            engine: str = "") -> dict:
    """SCA parts-guide lookup for a vehicle.

    Returns Inventory-formatted JSON: categories + a clean part list the
    inventory tab can import. Deterministic catalogue always; live SCA scrape
    augments when enabled and reachable.
    """
    catalogue = build_catalogue(rego, state, make, model, year, engine)
    if LIVE_SCRAPE:
        try:
            catalogue = await _live_enrich(catalogue)
        except Exception:
            catalogue.setdefault("note", "")
            catalogue["note"] = (catalogue["note"] + " Live scrape failed; using deterministic catalogue.").strip()
    return catalogue
