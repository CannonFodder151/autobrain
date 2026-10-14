"""QLD Fuel Prices state provider (AUT-2195).

Primary path: FuelPricesQLD DirectAPI v1.5 (Bearer subscription token).
Optional open-data fallback (www.fuelpricesqld.com.au) for one cycle behind
FUEL_QLD_USE_OPEN_FALLBACK so a partial direct-API outage does not break
Servo Spy.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger

from .base import _fetch_json, _first, _normalise_fuel_type, _now, _to_dt, _to_float
from .persistence import _ingest

logger = get_logger(__name__)

# DirectAPI short keys used by ``GetSitesPrices`` — P1..Pn keyed by FuelId.
# The mapping FuelId -> canonical fuel type is supplied by ``GetFuelTypes``.
_QLD_FUEL_FIELD_RE = re.compile(r"^P\d+$")


def _parse_qld_direct_sites(
    sites_raw: Any,
    brand_id_to_name: dict[int, str],
) -> list[dict]:
    """Parse ``GetFullSiteDetails`` payload into canonical station rows.

    DirectAPI shape: ``{"S": [{"S": <SiteId>, "A": <Address>, "N": <Name>,
    "B": <BrandId>, "P": <Postcode>, "G1"/"G2"/"G3": <GeoRegion>,
    "Lat": <lat>, "Lng": <lng>, "LastModified": <iso>}, ...]}``.
    Fields may appear in any order and extra keys may be present — ignore
    unknown keys, only read what we need.
    """
    rows = []
    if isinstance(sites_raw, dict):
        rows = sites_raw.get("S") or sites_raw.get("sites") or []
    elif isinstance(sites_raw, list):
        rows = sites_raw
    stations: list[dict] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        sid = _first(r, ["S", "SiteId", "Id"])
        if sid is None:
            continue
        brand_id = _first(r, ["B", "BrandId"])
        brand_name = brand_id_to_name.get(int(brand_id)) if brand_id is not None else None
        stations.append({
            "source": "qld",
            "source_id": str(sid),
            "brand": brand_name,
            "name": str(_first(r, ["N", "Name"]) or ""),
            "address": str(_first(r, ["A", "Address"]) or ""),
            "lat": _to_float(_first(r, ["Lat", "Latitude"])),
            "lon": _to_float(_first(r, ["Lng", "Longitude"])),
        })
    return stations


def _parse_qld_direct_prices(
    prices_raw: Any,
    fuel_id_to_name: dict[int, str],
) -> dict[str, list[tuple[str, float, datetime]]]:
    """Parse ``GetSitesPrices`` payload into site_id -> [(fuel, cents/litre, ts)].

    DirectAPI shape: ``{"S": [{"S": <SiteId>, "P1": <cents>, "P2": <cents>,
    ..., "LastUpdated": <iso>}, ...]}``. P1..Pn are keyed by FuelId (from
    ``GetFuelTypes``); prices are integer cents per litre (divide by 100 to
    get dollars). We keep dollars for downstream consistency with WA/NSW.
    """
    rows = []
    if isinstance(prices_raw, dict):
        rows = prices_raw.get("S") or prices_raw.get("sites") or []
    elif isinstance(prices_raw, list):
        rows = prices_raw
    out: dict[str, list[tuple[str, float, datetime]]] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        sid = _first(r, ["S", "SiteId", "Id"])
        if sid is None:
            continue
        sid = str(sid)
        ts = _to_dt(_first(r, ["LastUpdated", "LastModified"]))
        for k, v in r.items():
            if not isinstance(k, str) or not _QLD_FUEL_FIELD_RE.match(k):
                continue
            try:
                fuel_id = int(k[1:])
            except ValueError:
                continue
            fuel_name = fuel_id_to_name.get(fuel_id)
            ft = _normalise_fuel_type(fuel_name)
            price_dollars = _to_float(v)
            if price_dollars is not None:
                # DirectAPI returns integer cents/litre; WA/NSW already in
                # dollars. Caller may pass dollars or cents via the upstream
                # shape; downstream columns store dollars (FuelPrice.price).
                # Heuristic: if value looks like cents (> 50 with no decimal)
                # divide by 100, otherwise keep as-is. Real-world AU fuel
                # is always > 100 cents/litre, so this is safe.
                if price_dollars >= 50 and float(v).is_integer():
                    price_dollars = price_dollars / 100.0
            if ft and price_dollars is not None:
                out.setdefault(sid, []).append((ft, price_dollars, ts))
    return out


def _parse_qld_brands(brands_raw: Any) -> dict[int, str]:
    """Parse ``GetCountryBrands`` payload: ``[{"BrandId": <int>, "Name": <str>}, ...]``."""
    rows = brands_raw if isinstance(brands_raw, list) else []
    out: dict[int, str] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        bid = _first(r, ["BrandId", "Id"])
        name = _first(r, ["Name", "Brand"])
        if bid is not None and name:
            try:
                out[int(bid)] = str(name)
            except (TypeError, ValueError):
                continue
    return out


def _parse_qld_fuel_types(types_raw: Any) -> dict[int, str]:
    """Parse ``GetFuelTypes`` payload: ``[{"FuelId": <int>, "Name": <str>}, ...]``."""
    rows = types_raw if isinstance(types_raw, list) else []
    out: dict[int, str] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        fid = _first(r, ["FuelId", "Id"])
        name = _first(r, ["Name", "Fuel"])
        if fid is not None and name:
            try:
                out[int(fid)] = str(name)
            except (TypeError, ValueError):
                continue
    return out


def _parse_qld_geo_regions(regions_raw: Any, level: int) -> int | None:
    """Return the GeoRegionId for the given level (QLD = state = 3)."""
    rows = regions_raw if isinstance(regions_raw, list) else []
    for r in rows:
        if not isinstance(r, dict):
            continue
        if _first(r, ["GeoRegionLevel", "Level"]) == level:
            gid = _first(r, ["GeoRegionId", "Id"])
            if gid is not None:
                try:
                    return int(gid)
                except (TypeError, ValueError):
                    continue
    return None


# Public open-data fallback (kept for one cycle). Same parser as AUT-1817.
def _parse_qld(raw: Any) -> tuple[list[dict], dict[str, list[tuple[str, float, datetime]]]]:
    rows: list[dict] = []
    if isinstance(raw, dict):
        rows = raw.get("stations", raw.get("data", raw.get("features", [])))
    elif isinstance(raw, list):
        rows = raw
    stations: list[dict] = []
    prices: dict[str, list[tuple[str, float, datetime]]] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        sid = _first(r, ["id", "stationId", "code", "siteId"])
        if sid is None:
            continue
        sid = str(sid)
        stations.append({
            "source": "qld",
            "source_id": sid,
            "brand": (_first(r, ["brand"]) or None),
            "name": str(_first(r, ["name", "stationName"]) or ""),
            "address": str(_first(r, ["address"]) or ""),
            "lat": _to_float(_first(r, ["latitude", "lat"])),
            "lon": _to_float(_first(r, ["longitude", "lng"])),
        })
        raw_prices = _first(r, ["prices", "fuelPrices", "priceList"]) or {}
        if isinstance(raw_prices, list):
            for pr in raw_prices:
                ft = _normalise_fuel_type(_first(pr, ["fueltype", "type", "fuelType"]))
                price = _to_float(_first(pr, ["price", "priceCpl"]))
                if ft and price is not None:
                    prices.setdefault(sid, []).append((ft, price, _to_dt(_first(pr, ["lastupdated", "date", "effective_at"]))))
        elif isinstance(raw_prices, dict):
            for ft_raw, price in raw_prices.items():
                ft = _normalise_fuel_type(ft_raw)
                price = _to_float(price)
                if ft and price is not None:
                    prices.setdefault(sid, []).append((ft, price, _now()))
    return stations, prices


async def _fetch_qld_direct(client: httpx.AsyncClient | None) -> tuple[dict[int, str], dict[int, str], int | None, list[dict], dict[str, list[tuple[str, float, datetime]]]]:
    """Call the 4 QLD DirectAPI endpoints in sequence; return parsed dicts."""
    base = settings.FUEL_QLD_API_URL.rstrip("/")
    sub_token = settings.FUEL_QLD_API_KEY
    headers = {
        "Authorization": f"FPDAPI SubscriberToken={sub_token}",
        "Content-Type": "application/json",
    }
    country = settings.FUEL_QLD_COUNTRY_ID
    level = settings.FUEL_QLD_REGION_LEVEL
    brands = await _fetch_json(f"{base}/Subscriber/GetCountryBrands", headers=headers, params={"countryId": country}, client=client)
    fuel_types = await _fetch_json(f"{base}/Subscriber/GetFuelTypes", headers=headers, params={"countryId": country}, client=client)
    regions = await _fetch_json(f"{base}/Subscriber/GetCountryGeographicRegions", headers=headers, params={"countryId": country}, client=client)
    brand_map = _parse_qld_brands(brands)
    fuel_map = _parse_qld_fuel_types(fuel_types)
    geo_id = _parse_qld_geo_regions(regions, level)
    if geo_id is None:
        raise ValueError(f"QLD DirectAPI: no GeoRegionId at level {level}")
    sites_raw = await _fetch_json(f"{base}/Subscriber/GetFullSiteDetails", headers=headers, params={"countryId": country, "geoRegionLevel": level, "geoRegionId": geo_id}, client=client)
    prices_raw = await _fetch_json(f"{base}/Subscriber/GetSitesPrices", headers=headers, params={"countryId": country, "geoRegionLevel": level, "geoRegionId": geo_id}, client=client)
    stations = _parse_qld_direct_sites(sites_raw, brand_map)
    prices = _parse_qld_direct_prices(prices_raw, fuel_map)
    return brand_map, fuel_map, geo_id, stations, prices


async def ingest_qld_fuel_prices(db: AsyncSession, *, client: httpx.AsyncClient | None = None) -> dict:
    """QLD Servo Spy feed.

    Primary path: FuelPricesQLD DirectAPI v1.5 (Bearer subscription token).
    Falls back to the public open-data feed (www.fuelpricesqld.com.au) when
    ``settings.FUEL_QLD_USE_OPEN_FALLBACK`` is true, e.g. during a partial
    DirectAPI outage. Skipped entirely when ``FUEL_QLD_API_KEY`` is empty.
    """
    if not settings.FUEL_QLD_API_KEY:
        logger.info("fuel_qld_skipped_no_key")
        return {"source": "qld", "stations": 0, "prices": 0, "skipped": "no_api_key"}
    try:
        _, _, geo_id, stations, prices = await _fetch_qld_direct(client)
        logger.info("fuel_qld_direct_ok", geo_region_id=geo_id, stations=len(stations), prices=sum(len(v) for v in prices.values()))
        return await _ingest(db, "qld", stations, prices)
    except Exception as exc:  # noqa: BLE001
        if not settings.FUEL_QLD_USE_OPEN_FALLBACK:
            logger.error("fuel_qld_direct_failed", error=str(exc))
            return {"source": "qld", "stations": 0, "prices": 0, "error": str(exc)}
        logger.warning("fuel_qld_direct_failed_fallback_open", error=str(exc))
        raw = await _fetch_json(settings.FUEL_QLD_OPEN_DATA_URL, client=client)
        stations, prices = _parse_qld(raw)
        return await _ingest(db, "qld", stations, prices)