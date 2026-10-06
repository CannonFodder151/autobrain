"""VIC Fuel Saver (Servo Saver) state provider (AUT-1932).

Ingests the approved partner API at api.servosaver.com.au/v1/prices.
Requires FUEL_VIC_API_KEY and optionally FUEL_VIC_API_SECRET.
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


def _parse_vic(raw: Any) -> tuple[list[dict], dict[str, list[tuple[str, float, datetime]]]]:
    """Parse VIC Servo Saver API response.

    The VIC Servo Saver API returns a GeoJSON FeatureCollection with station
    properties containing brand, name, address, location, and fuel price data.
    Price fields are in cents per litre and are normalised to dollars (same as
    NSW/WA). Fuel type labels follow the canonical map used across all feeds.
    """
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
        sid = _first(p, ["stationid", "stationId", "id", "code"])
        if sid is None:
            continue
        sid = str(sid)
        # VIC packs price + fueltype into the same feature as the station.
        ft = _normalise_fuel_type(_first(p, ["fueltype", "fuelType", "fuel_type"]))
        price_cpl = _to_float(_first(p, ["price_cpl", "priceCpl", "price"]))
        if ft and price_cpl is not None:
            # API returns price in cents per litre; normalise to dollars
            price_dollars = price_cpl / 100.0 if price_cpl >= 50 else price_cpl
            prices.setdefault(sid, []).append((ft, price_dollars, _to_dt(_first(p, ["lastupdated", "lastUpdated", "effective_at", "date"]))))
        if not any(s["source_id"] == sid for s in stations):
            stations.append({
                "source": "vic",
                "source_id": sid,
                "brand": (_first(p, ["brand"]) or None),
                "name": str(_first(p, ["name"]) or ""),
                "address": str(_first(p, ["address"]) or ""),
                "lat": _to_float(_first(p, ["latitude", "lat"])),
                "lon": _to_float(_first(p, ["longitude", "lng"])),
            })
    return stations, prices


async def ingest_vic_fuel_saver(db: AsyncSession, *, client: httpx.AsyncClient | None = None) -> dict:
    """VIC Fuel Saver (Servo Saver) ingest.

    Calls ``FUEL_VIC_URL`` (``https://api.servosaver.com.au/v1/prices``) with
    Bearer auth using ``FUEL_VIC_API_KEY`` / ``FUEL_VIC_API_SECRET``.
    Skipped when either credential is missing or ``FUEL_VIC_ENABLED`` is False.

    AUT-4143: the endpoint is NXDOMAIN — the feed is dead. When enabled but the
    host does not resolve, this raises ``FuelFeedError`` instead of silently
    returning 0 stations, so the 6h beat logs the failure and the operator
    sees it rather than a stale/empty map.
    """
    if not settings.FUEL_VIC_ENABLED:
        logger.info("fuel_vic_skipped_disabled")
        return {"source": "vic", "stations": 0, "prices": 0, "skipped": "disabled"}
    if not settings.FUEL_VIC_API_KEY:
        logger.info("fuel_vic_skipped_no_key")
        return {"source": "vic", "stations": 0, "prices": 0, "skipped": "no_api_key"}
    headers = {"Authorization": f"Bearer {settings.FUEL_VIC_API_KEY}"}
    if settings.FUEL_VIC_API_SECRET:
        headers["X-Secret"] = settings.FUEL_VIC_API_SECRET
    raw = await _fetch_json(settings.FUEL_VIC_URL, headers=headers, client=client)
    stations, prices = _parse_vic(raw)
    return await _ingest(db, "vic", stations, prices)