"""Servo Spy fuel-price pipeline (AUT-1817) — deterministic, no AI.

Ingests three public open-data feeds into ``fuel_stations`` / ``fuel_prices``:

  * WA FuelWatch  : industryprd.fuelwatch.wa.gov.au (public, no key).
  * NSW FuelCheck : api.transport.nsw.gov.au/v1/fuel (free API key).
  * QLD Fuel Prices: fuelpricesqld.com.au (public open data).

Design: pure fetch + parse + upsert. Nothing is guessed, so the whole pipeline
is deterministic and costs zero 9Router spend (Phase 1c: deterministic first).
The only network boundary is ``_fetch_json`` (stubbed in tests). Radius queries
use great-circle distance in Python rather than PostGIS.

ponytail: WA + NSW shapes are pinned to the documented 2024/2025 schemas. QLD's
feed field names are best-effort (its open-data schema has changed historically);
if the live response differs, only the QLD parser needs a tweak, not the API.
VIC/SA/TAS/NT are intentionally out of MVP — they need a paid aggregator
(Informed Sources / MotorMouth), wired later as a premium enhancement.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.fuel_station import FuelPrice, FuelStation

logger = get_logger(__name__)

DEFAULT_FUEL_TYPES = ["E10", "91", "95", "98", "Diesel", "LPG"]

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
# QLD Fuel Prices (public open data; field names best-effort)
# --------------------------------------------------------------------------- #

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


async def _replace_station_prices(db: AsyncSession, station_id: str, prices: list[tuple[str, float, datetime]]) -> int:
    await db.execute(delete(FuelPrice).where(FuelPrice.station_id == station_id))
    for ft, price, eff in prices:
        db.add(FuelPrice(station_id=station_id, fuel_type=ft, price=price, effective_at=eff))
    return len(prices)


async def _ingest(db: AsyncSession, source: str, stations: list[dict], prices: dict[str, list]) -> dict:
    count_s, count_p = 0, 0
    for s in stations:
        station = await _upsert_station(db, s)
        ps = prices.get(s["source_id"], [])
        count_p += await _replace_station_prices(db, station.id, ps)
        count_s += 1
    return {"source": source, "stations": count_s, "prices": count_p}


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


async def ingest_qld_fuel_prices(db: AsyncSession, *, client: httpx.AsyncClient | None = None) -> dict:
    raw = await _fetch_json(settings.FUEL_QLD_API_URL, client=client)
    stations, prices = _parse_qld(raw)
    return await _ingest(db, "qld", stations, prices)


async def ingest_all_fuel(db: AsyncSession) -> dict:
    """Run every enabled feed; never let one feed's failure abort the others."""
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
    return summary
