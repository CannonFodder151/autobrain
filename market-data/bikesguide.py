"""BikeGuide scraper: pull live used-motorcycle listings for a search query.

BikesGuide is CarsGuide's motorcycle arm and runs the same Nuxt SSR stack, so
the __NUXT_DATA__ parsing logic is shared with carsguide.py. The listing
schema is identical (manu_year, odometer, make/model/variant, url_cg).

Gate: unlike CarsGuide, the bikesguide.com.au search path sits behind a
FingerprintJS redirect challenge. A plain HTTP client receives a small
fingerprint/redirect page with no __NUXT_DATA__ payload instead of the SSR
markup. We detect that and return an empty listing set deterministically (with
a note) so the valuation pipeline falls back cleanly instead of erroring.

ponytail: a browser channel (Playwright/undetected-chromium, same tier as the
CarsSales/Akamai upgrade path) is required to pass the fingerprint gate and get
live listings. BikesSales.com.au is likewise Akamai-protected. Until then this
provider is the deterministic degradation path, not a data source.
"""

import os

import httpx

from carsguide import _NUXT_SCRIPT, _filter_year, _map_listing, _parse_nuxt_listings

SEARCH_URL = os.getenv("BIKEGUIDE_SEARCH_URL", "https://www.bikesguide.com.au/search")
REQUEST_TIMEOUT = float(os.getenv("BIKEGUIDE_TIMEOUT", "45"))
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
MAX_LISTINGS = int(os.getenv("BIKEGUIDE_MAX_LISTINGS", "12"))


def _gated(html: str) -> bool:
    """True when the page is the FingerprintJS redirect challenge, not search markup."""
    if _NUXT_SCRIPT.search(html):
        return False
    return "fingerprint" in html.lower() or "tr_uuid" in html


async def search_bikesguide(query: str, year: int | None = None) -> dict:
    params = {"query": query}
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en-AU,en;q=0.9"}
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(SEARCH_URL, params=params, headers=headers)
        resp.raise_for_status()
        html = resp.text
    if _gated(html):
        return {
            "source": "bikesguide",
            "listings": [],
            "note": "gated: bikesguide requires a browser channel (FingerprintJS); see docs/market-data.md",
        }
    listings = []
    for raw in _parse_nuxt_listings(html):
        listing = _map_listing(raw)
        if listing and listing["price"]:
            listings.append(listing)
    listings = _filter_year(listings, year)
    return {"source": "bikesguide", "listings": listings[:MAX_LISTINGS]}
