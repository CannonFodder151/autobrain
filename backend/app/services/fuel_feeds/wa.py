"""WA FuelWatch state provider (AUT-1817).

Ingests the WA open-data feed from industryprd.fuelwatch.wa.gov.au.
Public, no API key required.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger

from .base import _fetch_json, _first, _normalise_fuel_type, _to_dt, _to_float
from .persistence import _ingest

logger = get_logger(__name__)


def _parse_wa_sites(raw: Any) -> list[dict]:
    rows = raw if isinstance(raw, list) else []
    out: list[dict] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        sid = _first(r, ["Sitedid", "SiteId", "siteId", "id"])
        if sid is None:
            continue
        out.append({
            "source": "wa",
            "source_id": str(sid),
            "brand": (_first(r, ["Brand", "brand"]) or None),
            "name": str(_first(r, ["Name", "Sitename", "name"]) or ""),
            "address": str(_first(r, ["Address", "address"]) or ""),
            "lat": _to_float(_first(r, ["Latitude", "lat"])),
            "lon": _to_float(_first(r, ["Longitude", "lng"])),
        })
    return out


def _parse_wa_prices(raw: Any) -> dict[str, list[tuple[str, float, datetime]]]:
    """Map WA SiteId -> list of (canonical_fuel, price_cpl, effective_at)."""
    rows = raw if isinstance(raw, list) else []
    out: dict[str, list[tuple[str, float, datetime]]] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        sid = _first(r, ["SiteId", "siteId"])
        if sid is None:
            continue
        ft = _normalise_fuel_type(_first(r, ["FuelCode", "fuelCode", "fuel_type"]))
        price = _to_float(_first(r, ["Price", "price"]))
        if not ft or price is None:
            continue
        out.setdefault(str(sid), []).append((ft, price, _to_dt(_first(r, ["PriceUpdatedDate", "lastupdated", "effective_at"]))))
    return out


async def ingest_wa_fuelwatch(db: AsyncSession, *, client: httpx.AsyncClient | None = None) -> dict:
    """WA FuelWatch ingest.

    Calls the public WA open-data endpoints (no auth required).
    """
    sites = await _fetch_json(settings.FUEL_WA_SITES_URL, client=client)
    prices = await _fetch_json(settings.FUEL_WA_PRICES_URL, client=client)
    return await _ingest(db, "wa", _parse_wa_sites(sites), _parse_wa_prices(prices))
