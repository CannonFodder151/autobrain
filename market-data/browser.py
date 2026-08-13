"""Playwright scrape worker for the gated market-data portals.

Runs as a subprocess (mirrors the rego-lookup-api browser.py pattern): a fresh
process means page loads / CDP hangs get real OS-level timeouts instead of
wedging uvicorn's event loop. The parent FastAPI process spawns this worker
and parses the JSON last-line on stdout.

Handled portals:
  - bikesguide: the FingerprintJS redirect gate auto-resolves in a real
    browser; we wait for the redirected page and either parse the Nuxt
    listing payload or report the page deterministically (parked / still
    gated) so the provider degrades without erroring.

ponytail: no undetected-chromium tier yet. bikesales.com.au's PerimeterX
hold-to-confirm + browser-fingerprint challenge is not reliably passable from
a datacenter host, so it is not wired here; add an undetected-chromedriver
worker (rego's uc_worker.py) if PerimeterX ever clears for this infra.
"""

import asyncio
import json
import re
import sys
from urllib.parse import urlencode

import carsguide
from carsguide import _NUXT_SCRIPT

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
PAGE_TIMEOUT_MS = 45000
GATE_WAIT_SECS = 40

_PARKED_MARKS = ("domain may be for sale", "may be for sale", "abovedomains")
_GATE_MARKS = ("fingerprint", "tr_uuid")


def _is_parked(html: str, text: str) -> bool:
    return any(m in html.lower() or m in text.lower() for m in _PARKED_MARKS)


def _still_gated(html: str, text: str) -> bool:
    if _NUXT_SCRIPT.search(html):
        return False
    return any(m in html.lower() or m in text.lower() for m in _GATE_MARKS)


def _emit(payload):
    print(json.dumps(payload), flush=True)


async def scrape_bikesguide(query: str, year: int | None) -> dict:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"ok": False, "kind": "gated",
                "note": "playwright not installed in image"}

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        except Exception as exc:
            return {"ok": False, "kind": "gated",
                    "note": f"bikesguide chromium launch failed: {type(exc).__name__}"}
        try:
            ctx = await browser.new_context(
                user_agent=UA, locale="en-AU",
                viewport={"width": 1280, "height": 900})
            page = await ctx.new_page()
            url = "https://www.bikesguide.com.au/search?" + urlencode({"query": query})
            try:
                await page.goto(url, wait_until="domcontentloaded",
                                timeout=PAGE_TIMEOUT_MS)
            except Exception as exc:
                return {"ok": False, "kind": "error",
                        "note": f"bikesguide browser nav failed: {type(exc).__name__}"}
            deadline = asyncio.get_event_loop().time() + GATE_WAIT_SECS
            while asyncio.get_event_loop().time() < deadline:
                await page.wait_for_timeout(2500)
                html = await page.content()
                text = re.sub(r"\s+", " ", await page.inner_text("body"))
                if _NUXT_SCRIPT.search(html):
                    listings = []
                    for raw in carsguide._parse_nuxt_listings(html):
                        listing = carsguide._map_listing(raw)
                        if listing and listing["price"]:
                            listings.append(listing)
                    listings = carsguide._filter_year(listings, year)
                    return {"ok": True, "listings": listings[:carsguide.MAX_LISTINGS]}
                if _is_parked(html, text):
                    return {"ok": False, "kind": "parked",
                            "note": "bikesguide.com.au is parked (domain for sale); no listings"}
            html = await page.content()
            text = re.sub(r"\s+", " ", await page.inner_text("body"))
            if _is_parked(html, text):
                return {"ok": False, "kind": "parked",
                        "note": "bikesguide.com.au is parked (domain for sale); no listings"}
            if _still_gated(html, text):
                return {"ok": False, "kind": "gated",
                        "note": "bikesguide fingerprint gate did not clear in browser"}
            return {"ok": False, "kind": "error",
                    "note": "bikesguide returned neither listings nor a known gate"}
        finally:
            await browser.close()


def main():
    portal, query = sys.argv[1], sys.argv[2]
    year = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].isdigit() else None
    result = asyncio.run(scrape_bikesguide(query, year))
    _emit(result)


if __name__ == "__main__":
    main()
