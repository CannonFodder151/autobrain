"""Fuel Feeds — common utilities and constants."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

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
    "pulp": "95", "premium unleaded": "95", "premium unleaded 95": "95", "95": "95", "u95": "u95",
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


def _day_bucket(ts: datetime) -> datetime:
    """Truncate a timestamp to its UTC day (00:00:00 UTC) for arbitration keys."""
    return ts.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)