"""BikeGuide scraper: pull live used-motorcycle listings for a search query.

BikesGuide is CarsGuide's motorcycle arm and runs the same Nuxt SSR stack, so
the __NUXT_DATA__ parsing logic is shared with carsguide.py. The listing
schema is identical (manu_year, odometer, make/model/variant, url_cg).

Gate: bikesguide.com.au sits behind a FingerprintJS redirect challenge on
plain HTTP (a small fingerprint/redirect page with no __NUXT_DATA__). As of
AUT-314 the domain is also parked ("may be for sale", served from an
AboveDomains parking host) — there are no listings behind the gate at all.
This provider therefore degrades deterministically: plain HTTP first (fast,
catches the parked page without spawning a browser), then the Playwright
channel (browser.py) when the page looks like a live gate, then an empty
listing set + note. The valuation pipeline never errors and never sees a
bogus sample.

ponytail: bikesales.com.au (the live AU bike marketplace) sits behind a
PerimeterX hold-to-confirm challenge that is not passable from this infra;
documented in docs/market-data.md. An undetected-chromium tier is the upgrade
path if PerimeterX clears.
"""

import asyncio
import json
import os
import re
import subprocess
import sys

import httpx

from carsguide import _NUXT_SCRIPT, _filter_year, _map_listing, _parse_nuxt_listings

SEARCH_URL = os.getenv("BIKEGUIDE_SEARCH_URL", "https://www.bikesguide.com.au/search")
REQUEST_TIMEOUT = float(os.getenv("BIKEGUIDE_TIMEOUT", "45"))
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
MAX_LISTINGS = int(os.getenv("BIKEGUIDE_MAX_LISTINGS", "12"))
BROWSER_ENABLED = os.getenv("BIKEGUIDE_BROWSER", "1").lower() in ("1", "true", "yes")

_PARKED_MARKS = ("domain may be for sale", "may be for sale", "abovedomains")


def _gated(html: str) -> bool:
    """True when the page is the FingerprintJS redirect challenge, not search markup."""
    if _NUXT_SCRIPT.search(html):
        return False
    return "fingerprint" in html.lower() or "tr_uuid" in html


def _parked(html: str) -> bool:
    return any(m in html.lower() for m in _PARKED_MARKS)


def _empty(note: str) -> dict:
    return {"source": "bikesguide", "listings": [], "note": note}


async def _browser_search(query: str, year: int | None) -> dict | None:
    """Run the Playwright worker in a subprocess (fresh process = reliable timeouts)."""
    cmd = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "browser.py"),
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
    params = {"query": query}
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en-AU,en;q=0.9"}
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(SEARCH_URL, params=params, headers=headers)
            resp.raise_for_status()
            html = resp.text
    except httpx.HTTPError as exc:
        return _empty(f"gated: bikesguide request failed ({exc.__class__.__name__})")

    if _parked(html):
        return _empty("parked: bikesguide.com.au domain is parked (for sale); no listings exist")
    if _gated(html):
        if BROWSER_ENABLED:
            return await _browser_search(query, year)
        return _empty("gated: bikesguide requires a browser channel (FingerprintJS); see docs/market-data.md")

    listings = []
    for raw in _parse_nuxt_listings(html):
        listing = _map_listing(raw)
        if listing and listing["price"]:
            listings.append(listing)
    listings = _filter_year(listings, year)
    return {"source": "bikesguide", "listings": listings[:MAX_LISTINGS]}
