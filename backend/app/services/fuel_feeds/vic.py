"""Fuel Feeds — VIC Fuel Saver (Servo Saver) parser."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger

from app.services.fuel_feeds.common import (
    _first,
    _to_float,
    _to_dt,
    _normalise_fuel_type,
)

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