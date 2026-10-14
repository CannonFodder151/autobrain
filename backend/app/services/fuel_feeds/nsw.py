"""NSW FuelCheck state provider (AUT-1817).

Ingests the NSW open-data feed from api.transport.nsw.gov.au/v1/fuel.
Requires a free API key (FUEL_NSW_API_KEY).
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


def _parse_nsw(raw: Any) -> tuple[list[dict], dict[str, list[tuple[str, float, datetime]]]]:
    features = []
    if isinstance(raw, dict):
        features = raw.get("features", [])
    elif isinstance(raw, list):
        features = raw
    stations: list[dict] = []
    prices: dict[str, list[tuple[str, float, datetime]]] = {}
    for f in features:
        if not isinstance(f, dict):
            continue
        p = f.get("properties", f) if isinstance(f, dict) else {}
        sid = _first(p, ["stationcode", "stationId", "id", "code"])
        if sid is None:
            continue
        sid = str(sid)
        # NSW packs price + fueltype into the same feature as the station.
        ft = _normalise_fuel_type(_first(p, ["fueltype", "fuelType", "fuel_type"]))
        price = _to_float(_first(p, ["price"]))
        if ft and price is not None:
            prices.setdefault(sid, []).append((ft, price, _to_dt(_first(p, ["lastupdated", "lastUpdated", "date"]))))
        if not any(s["source_id"] == sid for s in stations):
            stations.append({
                "source": "nsw",
                "source_id": sid,
                "brand": (_first(p, ["brand"]) or None),
                "name": str(_first(p, ["name"]) or ""),
                "address": str(_first(p, ["address"]) or ""),
                "lat": _to_float(_first(p, ["latitude", "lat"])),
                "lon": _to_float(_first(p, ["longitude", "lng"])),
            })
    return stations, prices


async def ingest_nsw_fuelcheck(db: AsyncSession, *, client: httpx.AsyncClient | None = None) -> dict:
    """NSW FuelCheck ingest.

    Calls the NSW API with the configured API key.
    Skipped when FUEL_NSW_API_KEY is not set.
    """
    if not settings.FUEL_NSW_API_KEY:
        logger.info("fuel_nsw_skipped_no_key")
        return {"source": "nsw", "stations": 0, "prices": 0, "skipped": "no_api_key"}
    headers = {"apikey": settings.FUEL_NSW_API_KEY, "Authorization": f"apikey {settings.FUEL_NSW_API_KEY}"}
    raw = await _fetch_json(settings.FUEL_NSW_URL, headers=headers, client=client)
    stations, prices = _parse_nsw(raw)
    return await _ingest(db, "nsw", stations, prices)