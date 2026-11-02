"""Fuel-feed provider package: split by state provider.

Re-exports the public surface previously exposed by the monolithic
``backend.app.services.fuel_price`` module so existing callers keep working.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from .base import (
    ALL_STATES,
    FeedHealth,
    FuelProvider,
    FuelProviderRegistry,
    SUPPORTED_STATES,
    _with_freshness,
    feed_health_to_dict,
)
from .nsw import NswFuelProvider
from .vic import VicFuelProvider
from .qld import QldFuelProvider
from .sa import SaFuelProvider
from .wa import WaFuelProvider

FEED_NAMES = {"WA": "WA FuelWatch (official)", "QLD": "FuelPriceQLD (partner)"}

# Registry of all providers
REGISTRY = FuelProviderRegistry()
for _p in (WaFuelProvider(), QldFuelProvider(), NswFuelProvider(), VicFuelProvider(), SaFuelProvider()):
    REGISTRY.register(_p)

# ACT is pending but not a dedicated provider file; register an inline provider
# so it appears in ALL_STATES and returns a pending feed health.
class _ActProvider(FuelProvider):
    state = "ACT"
    feed_name = "Unavailable"

    def is_available(self) -> bool:
        return False

    def fetch_stations(self) -> list[dict]:
        return []

    def get_health(self) -> FeedHealth:
        return FeedHealth(status="pending", last_success=None, last_error=None)


REGISTRY.register(_ActProvider())


def get_feed_health(state: str) -> dict:
    p = REGISTRY.get(state)
    if p is None:
        return {"state": state, "feed": "Unavailable", "status": "pending", "last_success": None, "last_error": None}
    h = p.get_health()
    return feed_health_to_dict(state, p.feed_name, h)


def get_stations(state: str) -> List[dict]:
    p = REGISTRY.get(state)
    if p is None or not p.is_available():
        return []
    return p.fetch_stations()


def fetch_state(state: str) -> dict:
    state = state.upper()
    if state in {"NSW", "ACT", "VIC"}:
        return {
            "state": state,
            "available": False,
            "message": f"Fuel prices for {state} are not available yet. Partner-feed keys pending.",
            "stations": [],
            "feed_status": get_feed_health(state),
        }
    if REGISTRY.get(state) is None:
        return {
            "state": state,
            "available": False,
            "message": f"Unknown state: {state}.",
            "stations": [],
            "feed_status": None,
        }
    p = REGISTRY.get(state)
    h = p.get_health()
    if h.status == "down":
        return {
            "state": state,
            "available": False,
            "message": f"Feed for {state} is currently down. Last error: {h.last_error or 'unknown'}.",
            "stations": [],
            "feed_status": get_feed_health(state),
        }
    stations = _with_freshness(p.fetch_stations())
    return {
        "state": state,
        "available": True,
        "message": None,
        "stations": stations,
        "feed_status": get_feed_health(state),
    }


def all_feed_health() -> List[dict]:
    return [get_feed_health(st) for st in ALL_STATES]


def mark_feed_down(state: str, error: str) -> None:
    p = REGISTRY.get(state)
    if p is not None and hasattr(p, "_health"):
        p._health.status = "down"
        p._health.last_error = error


def mark_feed_ok(state: str) -> None:
    p = REGISTRY.get(state)
    if p is not None and hasattr(p, "_health"):
        p._health.status = "ok"
        p._health.last_success = datetime.now(timezone.utc).isoformat()