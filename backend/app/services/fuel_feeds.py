"""Servo Spy fuel-price pipeline (AUT-1817) — deterministic, no AI.

Ingests three public open-data feeds into ``fuel_stations`` / ``fuel_prices``:

  * WA FuelWatch  : industryprd.fuelwatch.wa.gov.au (public, no key).
  * NSW FuelCheck : api.transport.nsw.gov.au/v1/fuel (free API key).
  * QLD Fuel Prices: FuelPricesQLD DirectAPI v1.5 (Bearer subscription token;
    AUT-2195). Optional open-data fallback (www.fuelpricesqld.com.au) for one
    cycle behind FUEL_QLD_USE_OPEN_FALLBACK so a partial direct-API outage
    does not break Servo Spy.

Design: pure fetch + parse + upsert. Nothing is guessed, so the whole pipeline
is deterministic and costs zero 9Router spend (Phase 1c: deterministic first).
The only network boundary is ``_fetch_json`` (stubbed in tests). Radius queries
use great-circle distance in Python rather than PostGIS.

ponytail: WA + NSW + QLD direct shapes are pinned to documented schemas; QLD
open-data parser kept behind a flag for one cycle then removed (AUT-2200+).
VIC/SA/TAS/NT are intentionally out of MVP — they need a paid aggregator
(Informed Sources / MotorMouth), wired later as a premium enhancement.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.fuel_station import FuelPrice, FuelPriceArbitration, FuelStation
from app.services.fuel_source_arbitration import (
    RawSourceObservation,
    arbitrate,
    source_authority,
)

logger = get_logger(__name__)

DEFAULT_FUEL_TYPES = ["E10", "91", "95", "98", "Diesel", "LPG"]

# 30-day rolling window for the /history endpoint (AUT-2386).
PRICE_HISTORY_DAYS = 30

# Canonical fuel-type map. Keys are lowercased raw labels seen across feeds.
_FUEL_TYPE_MAP: dict[str, str] = {
    "ulp": "91", "unleaded": "91", "unleaded 91": "91", "91": "91", "u91": "91",
    "pulp": "95", "premium unleaded": "95", "premium unleaded 95": "95", "95": "95", "u95": "95",
    "pulp98": "98", "premium unleaded 98": "98", "98": "98", "u98": "98",
    "e10": "E10", "ethanol": "E10",
    "diesel": "Diesel", "premium diesel": "Diesel", "diesel premium": "Diesel",
    "lpg": "LPG",
}

# Best-effort brand -> logo (frontend still maps by brand; null when unknown).
BRAND_LOGOS: dict[str, str] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km. Spherical-earth, <0.5% error at AU distances."""
    r = 6371.0088
    rad = math.pi / 180
    p1, p2 = lat1 * rad, lat2 * rad
    dphi = (lat2 - lat1) * rad
    dlmb = (lng2 - lng1) * rad
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _normalise_fuel_type(raw: Any) -> str | None:
    if raw is None:
        return None
    key = str(raw).strip().lower()
    if key in _FUEL_TYPE_MAP:
        return _FUEL_TYPE_MAP[key]
    up = str(raw).strip()
    if up in DEFAULT_FUEL_TYPES:
        return up
    return None


def _to_float(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    digits = "".join(ch for ch in str(raw) if ch.isdigit() or ch in ".-")
    try:
        return float(digits) if digits not in ("", "-", ".") else None
    except ValueError:
        return None


def _to_dt(raw: Any) -> datetime:
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(raw, timezone.utc)
    if isinstance(raw, str) and raw:
        s = raw.replace("Z", "+00:00")
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                d = datetime.strptime(s[:26], fmt)
                return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d
            except ValueError:
                continue
    return _now()


def _first(d: dict, aliases: list[str]) -> Any:
    for a in aliases:
        v = d.get(a)
        if v not in (None, "", []):
            return v
    return None


# --------------------------------------------------------------------------- #
# WA FuelWatch
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# NSW FuelCheck (GeoJSON FeatureCollection)
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# QLD Fuel Prices — DirectAPI v1.5 (AUT-2195) + optional open-data fallback
# --------------------------------------------------------------------------- #

# DirectAPI short keys used by ``GetSitesPrices`` — P1..Pn keyed by FuelId.
# The mapping FuelId -> canonical fuel type is supplied by ``GetFuelTypes``.
_QLD_FUEL_FIELD_RE = __import__("re").compile(r"^P\d+$")


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


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #

async def _upsert_station(db: AsyncSession, s: dict) -> FuelStation:
    existing = (await db.scalars(
        select(FuelStation).where(FuelStation.source == s["source"], FuelStation.source_id == s["source_id"])
    )).first()
    if existing:
        existing.brand = s["brand"]
        existing.name = s["name"]
        existing.address = s["address"]
        existing.lat = s["lat"]
        existing.lon = s["lon"]
        existing.updated_at = _now()
        return existing
    station = FuelStation(**s, updated_at=_now())
    db.add(station)
    await db.flush()
    return station


async def _replace_station_prices(
    db: AsyncSession,
    station_id: str,
    prices: list[tuple[str, float, datetime]],
    *,
    source_id: str,
) -> int:
    """Replace this source's price rows for a station with the new snapshot.

    Per AUT-2386, we now tag each row with the source that produced it so the
    arbitration pass can pick a deterministic winner across overlapping feeds.
    We only delete rows from THIS source (not all sources for the station) so
    that a NSW re-ingest does not blow away a WA observation of the same point.
    """
    await db.execute(
        delete(FuelPrice).where(
            FuelPrice.station_id == station_id, FuelPrice.source_id == source_id
        )
    )
    for ft, price, eff in prices:
        db.add(
            FuelPrice(
                station_id=station_id,
                fuel_type=ft,
                price=price,
                effective_at=eff,
                source_id=source_id,
            )
        )
    return len(prices)


async def _ingest(db: AsyncSession, source: str, stations: list[dict], prices: dict[str, list]) -> dict:
    count_s, count_p = 0, 0
    for s in stations:
        station = await _upsert_station(db, s)
        ps = prices.get(s["source_id"], [])
        count_p += await _replace_station_prices(db, station.id, ps, source_id=source)
        count_s += 1
    return {"source": source, "stations": count_s, "prices": count_p}


# --------------------------------------------------------------------------- #
# AUT-2386 — source arbitration pass
# --------------------------------------------------------------------------- #


def _day_bucket(ts: datetime) -> datetime:
    """Truncate a timestamp to its UTC day (00:00:00 UTC) for arbitration keys."""
    return ts.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


async def arbitrate_station_day(
    db: AsyncSession, station_id: str, fuel_type: str, day: datetime
) -> FuelPriceArbitration | None:
    """Pick the deterministic winner for one (station, fuel_type, UTC day).

    Reads every raw FuelPrice row that falls in that day bucket across all
    sources, runs :func:`app.services.fuel_source_arbitration.arbitrate`, and
    upserts the resulting FuelPriceArbitration row. Returns the row, or
    ``None`` if no source reported a price that day.
    """
    day_start = day.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    rows = list((await db.scalars(
        select(FuelPrice).where(
            FuelPrice.station_id == station_id,
            FuelPrice.fuel_type == fuel_type,
            FuelPrice.effective_at >= day_start,
            FuelPrice.effective_at < day_end,
            FuelPrice.source_id.isnot(None),
        )
    )).all())
    if not rows:
        return None

    obs = [
        RawSourceObservation(
            source_id=r.source_id,
            price=r.price,
            authority=source_authority(r.source_id),
            updated_at=r.effective_at,
        )
        for r in rows
        if r.source_id is not None
    ]
    result = arbitrate(obs)

    existing = await db.scalar(
        select(FuelPriceArbitration).where(
            FuelPriceArbitration.station_id == station_id,
            FuelPriceArbitration.fuel_type == fuel_type,
            FuelPriceArbitration.day == day_start,
        )
    )
    if existing is None:
        existing = FuelPriceArbitration(
            station_id=station_id,
            fuel_type=fuel_type,
            day=day_start,
        )
        db.add(existing)
    existing.source_id = result.winner_source
    existing.price = result.winner_price
    existing.arbitration_score = result.score
    existing.candidate_count = len(result.candidates)
    return existing


async def arbitrate_all_recent(
    db: AsyncSession, *, lookback_days: int = PRICE_HISTORY_DAYS
) -> int:
    """Re-run arbitration across every (station, fuel_type, day) in the cache.

    Called after a per-source ingest so the arbitration table reflects the
    latest set of overlapping sources. Cheap: one SELECT per station+fuel
    group, scoped to the 30-day history window. Returns the number of
    arbitration rows written.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    pairs = list((await db.execute(
        select(FuelPrice.station_id, FuelPrice.fuel_type, FuelPrice.effective_at)
        .where(FuelPrice.effective_at >= cutoff, FuelPrice.source_id.isnot(None))
    )).all())
    if not pairs:
        return 0
    written = 0
    seen: set[tuple[str, str, datetime]] = set()
    for station_id, fuel_type, eff in pairs:
        day = _day_bucket(eff)
        key = (station_id, fuel_type, day)
        if key in seen:
            continue
        seen.add(key)
        if await arbitrate_station_day(db, station_id, fuel_type, day) is not None:
            written += 1
    return written


# --------------------------------------------------------------------------- #
# Network boundary (single point — stubbed in tests)
# --------------------------------------------------------------------------- #

async def _fetch_json(url: str, *, headers: dict | None = None, params: dict | None = None, client: httpx.AsyncClient | None = None) -> Any:
    if client is not None:
        resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers={"User-Agent": settings.FUEL_INGEST_USER_AGENT}) as c:
        resp = await c.get(url, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()


# --------------------------------------------------------------------------- #
# Public ingest entrypoints
# --------------------------------------------------------------------------- #

async def ingest_wa_fuelwatch(db: AsyncSession, *, client: httpx.AsyncClient | None = None) -> dict:
    sites = await _fetch_json(settings.FUEL_WA_SITES_URL, client=client)
    prices = await _fetch_json(settings.FUEL_WA_PRICES_URL, client=client)
    return await _ingest(db, "wa", _parse_wa_sites(sites), _parse_wa_prices(prices))


async def ingest_nsw_fuelcheck(db: AsyncSession, *, client: httpx.AsyncClient | None = None) -> dict:
    if not settings.FUEL_NSW_API_KEY:
        logger.info("fuel_nsw_skipped_no_key")
        return {"source": "nsw", "stations": 0, "prices": 0, "skipped": "no_api_key"}
    headers = {"apikey": settings.FUEL_NSW_API_KEY, "Authorization": f"apikey {settings.FUEL_NSW_API_KEY}"}
    raw = await _fetch_json(settings.FUEL_NSW_URL, headers=headers, client=client)
    stations, prices = _parse_nsw(raw)
    return await _ingest(db, "nsw", stations, prices)


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


async def ingest_all_fuel(db: AsyncSession) -> dict:
    """Run every enabled feed; never let one feed's failure abort the others.

    AUT-2386: after the per-source ingests, run the arbitration pass so the
    per-day winner table is up to date for the next /history and /stations
    read. Arbitration failures are logged but do not poison the ingest
    summary — a station with no arbitration row simply falls back to the
    "latest row from any source" behaviour on the read path.
    """
    summary: dict[str, Any] = {}
    for name, fn in (
        ("wa", ingest_wa_fuelwatch),
        ("nsw", ingest_nsw_fuelcheck),
        ("qld", ingest_qld_fuel_prices),
    ):
        try:
            summary[name] = await fn(db)
        except Exception as exc:  # noqa: BLE001 — one bad feed must not sink the rest
            logger.error("fuel_ingest_failed", source=name, error=str(exc))
            summary[name] = {"source": name, "stations": 0, "prices": 0, "error": str(exc)}
    try:
        summary["arbitration"] = {
            "source": "arbitration",
            "rows": await arbitrate_all_recent(db),
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("fuel_arbitration_failed", error=str(exc))
        summary["arbitration"] = {"source": "arbitration", "rows": 0, "error": str(exc)}
    return summary
