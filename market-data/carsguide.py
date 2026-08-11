"""CarsGuide scraper: pull live used-car listings for a search query.

CarsGuide's search page (/search?query=...) is a Nuxt SSR app. The server
renders the first result page into the HTML and embeds the full listing set
in a <script id="__NUXT_DATA__"> JSON payload (de-duplicated array; values
are resolved by index). We parse that payload — no browser, no JS.

Response shape follows docs/market-data.md so the backend's
_market_data._parse_provider_response/_map_listing can consume it directly:
{"source": "carsguide", "listings": [{title, price, year, odometer_km,
source, url}]}.

ponytail: CarsGuide-only today. CarSales.com.au sits behind Akamai (403 on
plain HTTP); a Playwright/undetected channel like rego-lookup's would be the
upgrade path. Add a `carsales` provider in this file and merge under the
SearchResponse "source" key when needed.
"""

import json
import os
import re

import httpx

SEARCH_URL = os.getenv("CARSGUIDE_SEARCH_URL", "https://www.carsguide.com.au/search")
BASE_URL = os.getenv("CARSGUIDE_BASE_URL", "https://www.carsguide.com.au")
REQUEST_TIMEOUT = float(os.getenv("CARSGUIDE_TIMEOUT", "45"))
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
MAX_LISTINGS = int(os.getenv("CARSGUIDE_MAX_LISTINGS", "12"))

_NUXT_SCRIPT = re.compile(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', re.S)


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
    nearby = [l for l in listings if l["year"] and abs(l["year"] - year) <= 2]
    if len(nearby) >= 3:
        return nearby
    return listings


async def search_carsguide(query: str, year: int | None = None) -> dict:
    # Search the model line broadly, then post-filter by year in Python so a
    # narrow year never collapses the sample (query text stays make/model).
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
