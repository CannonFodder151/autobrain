"""Servo Spy fuel-price pipeline (AUT-1817) — deterministic, no AI.

Ingests four public open-data feeds into ``fuel_stations`` / ``fuel_prices``:

  * SA SAFPIS     : SA DirectAPI v1.2 (Bearer subscription token; AUT-2406).
    Same aggregator (Informed Sources) as QLD, but prices are tenths of a
    cent (1356.0 = 135.6 c/L). Skipped when FUEL_SA_API_KEY is empty.
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
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any

import httpx
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.fuel_station import FuelPrice, FuelStation

logger = get_logger(__name__)

DEFAULT_FUEL_TYPES = ["E10", "91", "95", "98", "Diesel", "LPG"]

# --------------------------------------------------------------------------- #
# Multi-source arbitration (AUT-2381)
# --------------------------------------------------------------------------- #

# Tunables. Kept module-level so a follow-up admin override can be wired
# without a code change.
ARBITRATION_STALE_HOURS = 2.0      # freshness weight hits 0 after this age
ARBITRATION_OUTLIER_CPL = 30.0     # > this gap from regional median -> flag
ARBITRATION_SCORE_FRESHNESS_W = 2  # weight on freshness_weight
ARBITRATION_SCORE_TRUST_W = 3      # weight on source_trust
ARBITRATION_SCORE_CONSISTENCY_W = 1  # weight on consistency_bonus


class SourceTrust(IntEnum):
    """Authoritative rank of upstream fuel-price sources. Higher = more trusted.

    GOVERNMENT_FREE is the strongest signal (official open-data, no key, CC
    licence, paid for by taxpayers). RETAIL_FREE covers free, keyless third
    parties (projectzerothree, FuelPricesQLD open-data). GOVERNMENT_PAID is a
    government feed behind a paid subscription (FuelPricesQLD DirectAPI). The
    IntEnum value IS the score (so we don't carry a separate column).
    """

    CROWDSCRAPED = 1
    GOVERNMENT_PAID = 2
    RETAIL_FREE = 3
    GOVERNMENT_FREE = 4


# Map of canonical upstream id -> SourceTrust. Keep keys in sync with the
# ``source`` column we write into ``fuel_prices.source``.
SOURCE_TRUST: dict[str, SourceTrust] = {
    # Government free, no key required.
    "wa": SourceTrust.GOVERNMENT_FREE,        # WA FuelWatch
    "nsw": SourceTrust.GOVERNMENT_FREE,       # NSW FuelCheck
    # Government paid (Bearer subscription).
    "qld_direct": SourceTrust.GOVERNMENT_PAID,
    # Retail free (third party, no key).
    "sa": SourceTrust.GOVERNMENT_PAID,        # SA SAFPIS (AUT-2406)
    "qld": SourceTrust.RETAIL_FREE,           # QLD open-data fallback
    "7eleven": SourceTrust.RETAIL_FREE,       # projectzerothree.info
    # Crowdscraped (rescue-the-moment override; reserved for a future AUT).
    "crowd": SourceTrust.CROWDSCRAPED,
}


@dataclass(frozen=True)
class PriceCandidate:
    """One upstream price observation for the arbitration step."""

    source: str               # "wa", "nsw", "qld_direct", "sa", "7eleven", "crowd"
    price: float              # dollars per litre (matches FuelPrice.price)
    fuel_type: str            # canonical: 91, 95, 98, E10, Diesel, LPG
    effective_at: datetime    # upstream's "as of" timestamp (tz-aware)
    station_id: str | None = None  # optional — only used for logging


@dataclass(frozen=True)
class ArbitrationResult:
    """Outcome of the per-(station, fuel_type, day) arbitration."""

    best_source: str
    best_price: float
    best_effective_at: datetime
    source_score: float
    flagged_sources: frozenset[str]  # candidates marked as consistency outliers


def _freshness_weight(candidate: PriceCandidate, *, now: datetime | None = None) -> float:
    """Linear decay from 1.0 (now) to 0.0 (>= ARBITRATION_STALE_HOURS old).

    Naive timestamps are treated as UTC. Naive ``now`` is also treated as UTC
    so the helper is safe to call from a test that has not faked tzinfo.
    """
    ts = candidate.effective_at
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    current = (now or datetime.now(timezone.utc))
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    age_h = max(0.0, (current - ts).total_seconds() / 3600.0)
    if age_h >= ARBITRATION_STALE_HOURS:
        return 0.0
    return round(1.0 - (age_h / ARBITRATION_STALE_HOURS), 4)


def _consistency_bonus(candidate: PriceCandidate, all_candidates: list[PriceCandidate]) -> float:
    """Return 1.0 if the price is within ARBITRATION_OUTLIER_CPL of the regional
    median (other candidates), 0.0 if it is an outlier, 0.5 if it is alone.

    A single candidate cannot be inconsistent with itself, so a lone row gets
    a neutral 0.5 rather than 0.0 (we still want to surface a "trust" answer).
    """
    if len(all_candidates) <= 1:
        return 0.5
    others = [c.price for c in all_candidates if c is not candidate]
    if not others:
        return 0.5
    others_sorted = sorted(others)
    mid = len(others_sorted) // 2
    if len(others_sorted) % 2:
        median = others_sorted[mid]
    else:
        median = 0.5 * (others_sorted[mid - 1] + others_sorted[mid])
    if abs(candidate.price - median) > ARBITRATION_OUTLIER_CPL:
        return 0.0
    return 1.0


def _score_candidate(candidate: PriceCandidate, all_candidates: list[PriceCandidate], *, now: datetime | None = None) -> float:
    """Composite score per the AUT-2381 formula.

    ``score = freshness_weight * 2 + source_trust * 3 + consistency * 1``.

    Higher is better. Trust dominates freshness dominates consistency, but
    a stale-but-trusted source can still lose to a fresh-but-less-trusted one
    when the gap is wide enough (e.g. 4*3=12 vs 1.0*2+2*3=8).
    """
    trust = SOURCE_TRUST.get(candidate.source, SourceTrust.CROWDSCRAPED)
    freshness = _freshness_weight(candidate, now=now)
    consistency = _consistency_bonus(candidate, all_candidates)
    return (
        freshness * ARBITRATION_SCORE_FRESHNESS_W
        + int(trust) * ARBITRATION_SCORE_TRUST_W
        + consistency * ARBITRATION_SCORE_CONSISTENCY_W
    )


def select_best_price(candidates: list[PriceCandidate], *, now: datetime | None = None) -> ArbitrationResult | None:
    """Pick the best candidate by AUT-2381's score. Pure, deterministic, no I/O.

    Returns ``None`` for an empty input. Ties break on (higher source trust,
    fresher timestamp, lexicographic source id) so the answer is stable across
    runs — important because the winner is persisted to ``fuel_prices``.
    """
    if not candidates:
        return None
    scored = [(c, _score_candidate(c, candidates, now=now)) for c in candidates]
    # Sort: highest score, then higher trust, then fresher, then stable id.
    scored.sort(
        key=lambda pair: (
            -pair[1],
            -int(SOURCE_TRUST.get(pair[0].source, SourceTrust.CROWDSCRAPED)),
            -pair[0].effective_at.timestamp(),
            pair[0].source,
        )
    )
    winner, score = scored[0]
    flagged = frozenset(
        c.source
        for c in candidates
        if c is not winner and _consistency_bonus(c, candidates) == 0.0
    )
    return ArbitrationResult(
        best_source=winner.source,
        best_price=winner.price,
        best_effective_at=winner.effective_at,
        source_score=round(float(score), 4),
        flagged_sources=flagged,
    )


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



# --------------------------------------------------------------------------- #
# SA SAFPIS (SA Fuel Pricing Information Scheme, AUT-2406)
# Same DirectAPI shape as QLD — same aggregator (Informed Sources). One
# critical difference: SA returns prices in **tenths of a cent** (e.g. 1356.0 =
# 135.6 c/L). Drop the QLD integer-cents heuristic.
# --------------------------------------------------------------------------- #

# Per the SAFPIS API v1.2 guide: a P# cell of 9999.0 means the product is not
# sold at that site. We must NOT store it as $99.99/L.
_SA_UNAVAILABLE_PRICE = 9999.0


def _parse_sa_direct_prices(
    prices_raw: Any,
    fuel_id_to_name: dict[int, str],
) -> dict[str, list[tuple[str, float, datetime]]]:
    """Parse SA ``GetSitesPrices`` payload: tenths-of-a-cent -> cents/litre.

    DirectAPI shape: ``{"S": [{"S": <SiteId>, "P1": <tenths-of-a-cent>,
    "P2": <tenths-of-a-cent>, ..., "LastUpdated": <iso>}, ...]}``. We convert
    tenths-of-a-cent -> cents per litre (divide by 10). Cells equal to
    ``_SA_UNAVAILABLE_PRICE`` (9999.0) are dropped — that site simply doesn't
    sell that fuel.
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
            raw_value = _to_float(v)
            if raw_value is None or ft is None:
                continue
            price_cpl = raw_value / 10.0
            if price_cpl == _SA_UNAVAILABLE_PRICE:
                # SAFPIS: 9999.0 c/L (== 99990 tenths-of-a-cent) means the
                # product is not sold at this site. Drop, never store 0.
                continue
            out.setdefault(sid, []).append((ft, price_cpl, ts))
    return out


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


PRICE_HISTORY_DAYS = 30  # AUT-2375: retain 30 days for /history chart


async def _replace_station_prices(
    db: AsyncSession,
    station_id: str,
    source: str,
    prices: list[tuple[str, float, datetime]],
) -> int:
    """Upsert latest price per (station, fuel_type, source) and keep 30-day history.

    AUT-2381 + AUT-2375 merge:
      * Source-keyed (AUT-2381): each upstream feed keeps its own row so the
        arbitration step (``arbitrate_station_prices``) can see what every
        source said this cycle.
      * 30-day retention (AUT-2375): don't wipe prior rows on every ingest —
        prune anything older than PRICE_HISTORY_DAYS in one DELETE so the
        /api/v1/fuel/stations/{id}/history endpoint serves a real series.
      * Duplicates re-published with the same (fuel_type, effective_at) for
        THIS source are deleted before insert (the newer value wins).
    """
    from datetime import timedelta

    if prices:
        keys = list({(ft, eff) for ft, _, eff in prices})
        if keys:
            conditions = [
                (FuelPrice.station_id == station_id)
                & (FuelPrice.source == source)
                & (FuelPrice.fuel_type == ft)
                & (FuelPrice.effective_at == eff)
                for ft, eff in keys
            ]
            await db.execute(delete(FuelPrice).where(or_(*conditions)))
    cutoff = datetime.now(timezone.utc) - timedelta(days=PRICE_HISTORY_DAYS)
    await db.execute(
        delete(FuelPrice).where(
            FuelPrice.station_id == station_id,
            FuelPrice.effective_at < cutoff,
        )
    )
    for ft, price, eff in prices:
        db.add(
            FuelPrice(
                station_id=station_id,
                fuel_type=ft,
                price=price,
                effective_at=eff,
                source=source,
            )
        )
    return len(prices)


async def arbitrate_station_prices(db: AsyncSession, station_id: str) -> int:
    """Run AUT-2381 arbitration across every (fuel_type) for a station.

    Looks at every FuelPrice row currently attached to the station, builds
    PriceCandidate objects, calls ``select_best_price`` per fuel_type, and
    writes the winner's (best_source, source_score, flag_reason) back to each
    row in that group. Returns the number of fuel types arbitrated.

    Pure SQL + in-memory arithmetic; no network, no AI. Safe to call inside
    an existing transaction.
    """
    rows = list(
        (
            await db.scalars(
                select(FuelPrice).where(FuelPrice.station_id == station_id)
            )
        ).all()
    )
    by_fuel: dict[str, list[FuelPrice]] = {}
    for r in rows:
        by_fuel.setdefault(r.fuel_type, []).append(r)

    arbitrated = 0
    now = _now()
    for fuel_type, group in by_fuel.items():
        candidates = [
            PriceCandidate(
                source=r.source or "unknown",
                price=r.price,
                fuel_type=fuel_type,
                effective_at=r.effective_at,
                station_id=station_id,
            )
            for r in group
        ]
        result = select_best_price(candidates, now=now)
        if result is None:
            continue
        winner_id = None
        for r in group:
            r.best_source = result.best_source
            r.source_score = result.source_score
            if r.source in result.flagged_sources:
                r.flag_reason = "outlier>30cpl"
            elif r.source == result.best_source:
                r.flag_reason = None
                winner_id = r.id
            else:
                r.flag_reason = None
        arbitrated += 1
        logger.info(
            "fuel_arbitration",
            station_id=station_id,
            fuel_type=fuel_type,
            best_source=result.best_source,
            best_price=result.best_price,
            score=result.source_score,
            flagged=sorted(result.flagged_sources),
        )
    return arbitrated


async def _ingest(db: AsyncSession, source: str, stations: list[dict], prices: dict[str, list]) -> dict:
    count_s, count_p = 0, 0
    arbitrated_stations: set[str] = set()
    for s in stations:
        station = await _upsert_station(db, s)
        ps = prices.get(s["source_id"], [])
        count_p += await _replace_station_prices(db, station.id, source, ps)
        arbitrated_stations.add(station.id)
        count_s += 1
    for sid in arbitrated_stations:
        await arbitrate_station_prices(db, sid)
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



async def _fetch_sa_direct(client: httpx.AsyncClient | None) -> tuple[list[dict], dict[str, list[tuple[str, float, datetime]]]]:
    """Call the 4 SA SAFPIS endpoints; reuse QLD parsers for sites/brands/fuel
    (same aggregator, same shape) and the SA-specific price parser for the
    tenths-of-a-cent -> c/L conversion + 9999.0 sentinel drop."""
    base = settings.FUEL_QLD_API_URL.rstrip("/")  # same upstream base
    sub_token = settings.FUEL_SA_API_KEY
    headers = {
        "Authorization": f"FPDAPI SubscriberToken={sub_token}",
        "Content-Type": "application/json",
    }
    country = settings.FUEL_QLD_COUNTRY_ID
    geo_id = settings.FUEL_SA_GEO_REGION_ID
    brands = await _fetch_json(f"{base}/Subscriber/GetCountryBrands", headers=headers, params={"countryId": country}, client=client)
    fuel_types = await _fetch_json(f"{base}/Subscriber/GetFuelTypes", headers=headers, params={"countryId": country}, client=client)
    sites_raw = await _fetch_json(f"{base}/Subscriber/GetFullSiteDetails", headers=headers, params={"countryId": country, "geoRegionLevel": 3, "geoRegionId": geo_id}, client=client)
    prices_raw = await _fetch_json(f"{base}/Subscriber/GetSitesPrices", headers=headers, params={"countryId": country, "geoRegionLevel": 3, "geoRegionId": geo_id}, client=client)
    brand_map = _parse_qld_brands(brands)
    fuel_map = _parse_qld_fuel_types(fuel_types)
    stations = _parse_qld_direct_sites(sites_raw, brand_map)
    prices = _parse_sa_direct_prices(prices_raw, fuel_map)
    return stations, prices


async def ingest_sa_fuel(db: AsyncSession, *, client: httpx.AsyncClient | None = None) -> dict:
    """SA SAFPIS Servo Spy feed (AUT-2406).

    Skipped entirely when ``FUEL_SA_API_KEY`` is empty. Same DirectAPI shape as
    QLD, but prices are in tenths of a cent (1356.0 = 135.6 c/L) and ``9999.0``
    means the product is unavailable at that site. Reuses the QLD
    site/brand/fuel-type parsers (Informed Sources = same aggregator) and the
    dedicated ``_parse_sa_direct_prices`` for the price conversion.
    """
    if not settings.FUEL_SA_API_KEY:
        logger.info("fuel_sa_skipped_no_key")
        return {"source": "sa", "stations": 0, "prices": 0, "skipped": "no_api_key"}
    try:
        stations, prices = await _fetch_sa_direct(client)
        logger.info("fuel_sa_direct_ok", geo_region_id=settings.FUEL_SA_GEO_REGION_ID, stations=len(stations), prices=sum(len(v) for v in prices.values()))
        return await _ingest(db, "sa", stations, prices)
    except Exception as exc:  # noqa: BLE001
        logger.error("fuel_sa_direct_failed", error=str(exc))
        return {"source": "sa", "stations": 0, "prices": 0, "error": str(exc)}


async def ingest_all_fuel(db: AsyncSession) -> dict:
    """Run every enabled feed; never let one feed's failure abort the others."""
    summary: dict[str, Any] = {}
    for name, fn in (
        ("wa", ingest_wa_fuelwatch),
        ("nsw", ingest_nsw_fuelcheck),
        ("sa", ingest_sa_fuel),
        ("qld", ingest_qld_fuel_prices),
    ):
        try:
            summary[name] = await fn(db)
        except Exception as exc:  # noqa: BLE001 — one bad feed must not sink the rest
            logger.error("fuel_ingest_failed", source=name, error=str(exc))
            summary[name] = {"source": name, "stations": 0, "prices": 0, "error": str(exc)}
    return summary
