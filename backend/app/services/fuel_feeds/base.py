"""Common base classes and registry for state fuel-feed providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

SUPPORTED_STATES = {"WA", "QLD"}
PENDING_STATES = {"NSW", "ACT", "VIC"}
ALL_STATES = ["WA", "QLD", "NSW", "ACT", "VIC"]


@dataclass
class FeedHealth:
    status: str  # "ok" | "down" | "pending"
    last_success: Optional[str] = None
    last_error: Optional[str] = None


@dataclass
class Station:
    id: str
    name: str
    state: str
    suburb: str
    price_cpl: float
    fuel_type: str
    updated_at: str


class FuelProvider(ABC):
    """Interface every state provider implements."""

    state: str
    feed_name: str

    @abstractmethod
    def is_available(self) -> bool:
        """Return True when live prices can be served for this state."""

    @abstractmethod
    def fetch_stations(self) -> List[dict]:
        """Return the list of station price dicts for this state."""

    def get_health(self) -> FeedHealth:
        return FeedHealth(status="ok" if self.is_available() else "pending")


class FuelProviderRegistry:
    """Registry of state -> FuelProvider instances."""

    def __init__(self) -> None:
        self._providers: Dict[str, FuelProvider] = {}

    def register(self, provider: FuelProvider) -> None:
        self._providers[provider.state] = provider

    def get(self, state: str) -> Optional[FuelProvider]:
        return self._providers.get(state)

    def states(self) -> List[str]:
        return list(self._providers.keys())

    def available_states(self) -> List[str]:
        return [s for s, p in self._providers.items() if p.is_available()]

    def all_states(self) -> List[str]:
        return list(self._providers.keys())


def _freshness_minutes(updated_at: str) -> Optional[int]:
    try:
        dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return int((now - dt).total_seconds() / 60)
    except Exception:
        return None


def _with_freshness(stations: List[dict]) -> List[dict]:
    out = []
    for s in stations:
        s2 = dict(s)
        s2["freshness_minutes"] = _freshness_minutes(s.get("updated_at", ""))
        out.append(s2)
    return out


def feed_health_to_dict(state: str, feed_name: str, health: FeedHealth) -> dict:
    return {
        "state": state,
        "feed": feed_name,
        "status": health.status,
        "last_success": health.last_success,
        "last_error": health.last_error,
    }