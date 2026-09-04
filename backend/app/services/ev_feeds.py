"""Electric Spy Open Charge Map (OCM) ingest (AUT-2435).

Pulls a radius of charging stations from OCM and normalises them into
``ChargingStation`` + ``ChargingConnector`` rows. Mirrors the structure of
``fuel_feeds``: deterministic parser, no AI, easy to test.

API: https://api.openchargemap.io/v3/poi/ — public, free tier with an API key.
We treat the API key as optional: anonymous calls still return limited results
during outages / quota exhaustion, so the UI keeps working with stale cached
data.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.ev_station import ChargingConnector, ChargingStation

logger = logging.getLogger(__name__)

OCM_URL = "https://api.openchargemap.io/v3/poi/"
DEFAULT_RADIUS_KM = 25
DEFAULT_LIMIT = 50

EV_ATTRIBUTION = [
    "Open Charge Map - https://openchargemap.org (CC BY-SA 4.0)",
]
ATTRIBUTION_HEADER = "X-EV-Data-Attribution"

# Canonical connector types shown to the user. Anything outside this set
# falls back to the OCM raw title so we don't silently drop information.
KNOWN_CONNECTOR_TYPES = {
    "Type 2",
    "CCS2",
    "CCS",
    "CHAdeMO",
    "Tesla",
    "J1772",
    "Type 1",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km. Reused so fuel/ev share the same math."""
    from math import asin, cos, radians, sin, sqrt
    r = 6371.0
    p1, p2 = radians(lat1), radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lng2 - lng1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * r * asin(sqrt(a))


def _connector_type(raw: object) -> str | None:
    if not isinstance(raw, dict):
        return None
    nested = raw.get("ConnectionType") or raw.get("connection_type")
    if isinstance(nested, dict):
        title = nested.get("Title") or nested.get("title") or nested.get("Name")
    else:
        title = raw.get("Title") or raw.get("title") or raw.get("Name")
    if not isinstance(title, str):
        return None
    title = title.strip()
    if not title:
        return None
    return title


def _max_power_kw(conn: dict) -> float | None:
    raw = conn.get("PowerKW") or conn.get("powerKW") or conn.get("RatedPowerKW")
    if raw is None:
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def _status(conn: dict) -> str | None:
    raw = conn.get("StatusType") or conn.get("status_type") or conn.get("Status") or conn.get("status")
    if isinstance(raw, dict):
        raw = raw.get("Title") or raw.get("title") or raw.get("Name")
    if not isinstance(raw, str):
        return None
    raw = raw.strip()
    return raw or None


def _cost_per_kwh(conn: dict) -> float | None:
    """OCM carries pricing as a free-text comment; if it parses as a float
    we use it, else None. Keeps us deterministic: no AI guessing prices."""
    raw = (
        conn.get("UsageCost")
        or conn.get("usage_cost")
        or conn.get("Cost")
    )
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        v = float(raw)
        return v if v > 0 else None
    if isinstance(raw, str):
        text = raw.replace("$", "").replace("/kWh", "").replace("AUD", "").strip()
        try:
            v = float(text.split()[0])
        except (ValueError, IndexError):
            return None
        return v if v > 0 else None
    return None


def _parse_station(raw: dict) -> tuple[dict, list[dict]] | None:
    if not isinstance(raw, dict):
        return None
    address_info = raw.get("AddressInfo") or {}
    lat = address_info.get("Latitude")
    lon = address_info.get("Longitude")
    if lat is None or lon is None:
        return None
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return None
    address_parts = [
        address_info.get("AddressLine1"),
        address_info.get("Town"),
        address_info.get("StateOrProvince"),
    ]
    address = ", ".join(p for p in address_parts if isinstance(p, str) and p.strip()) or None
    operator = raw.get("OperatorInfo") or {}
    network = operator.get("Title") if isinstance(operator, dict) else None
    station = {
        "ocm_id": raw.get("ID"),
        "network": network if isinstance(network, str) else None,
        "name": address_info.get("Title") or "Charging Station",
        "address": address,
        "lat": lat,
        "lon": lon,
    }
    connectors_raw = raw.get("Connections") or []
    connectors: list[dict] = []
    if isinstance(connectors_raw, list):
        for c in connectors_raw:
            if not isinstance(c, dict):
                continue
            ct = _connector_type(c)
            if not ct:
                continue
            connectors.append(
                {
                    "connector_type": ct,
                    "max_power_kw": _max_power_kw(c),
                    "cost_per_kwh": _cost_per_kwh(c),
                    "status": _status(c),
                }
            )
    return station, connectors


async def fetch_ocm(
    *,
    lat: float,
    lon: float,
    radius_km: float = DEFAULT_RADIUS_KM,
    limit: int = DEFAULT_LIMIT,
) -> list[dict]:
    """Best-effort fetch from Open Charge Map. Empty list on failure."""
    params: dict[str, object] = {
        "latitude": lat,
        "longitude": lon,
        "distance": radius_km,
        "distanceunit": "KM",
        "maxresults": limit,
        "compact": "true",
        "verbose": "false",
    }
    api_key = getattr(settings, "OCM_API_KEY", None)
    if api_key:
        params["key"] = api_key
    ua = getattr(settings, "OCM_USER_AGENT", None) or "AutoBrain-ElectricSpy/1.0"
    headers = {"User-Agent": ua}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(OCM_URL, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("OCM fetch failed: %s", exc)
        return []
    if not isinstance(data, list):
        return []
    parsed: list[dict] = []
    for row in data:
        out = _parse_station(row)
        if out:
            parsed.append({"station": out[0], "connectors": out[1]})
    return parsed


async def refresh_radius(
    db: AsyncSession,
    *,
    lat: float,
    lon: float,
    radius_km: float = DEFAULT_RADIUS_KM,
    limit: int = DEFAULT_LIMIT,
) -> int:
    """Replace cached stations inside (lat, lon, radius_km) with a fresh OCM
    pull. Returns the number of stations written."""
    rows = await fetch_ocm(lat=lat, lon=lon, radius_km=radius_km, limit=limit)
    if not rows:
        return 0
    await db.execute(delete(ChargingStation))
    written = 0
    for row in rows:
        s = row["station"]
        station = ChargingStation(
            ocm_id=s["ocm_id"],
            network=s["network"],
            name=s["name"],
            address=s["address"],
            lat=s["lat"],
            lon=s["lon"],
        )
        for c in row["connectors"]:
            station.connectors.append(
                ChargingConnector(
                    connector_type=c["connector_type"],
                    max_power_kw=c["max_power_kw"],
                    cost_per_kwh=c["cost_per_kwh"],
                    status=c["status"],
                )
            )
        db.add(station)
        written += 1
    await db.commit()
    return written


def is_known_connector_type(name: str) -> bool:
    return name in KNOWN_CONNECTOR_TYPES
