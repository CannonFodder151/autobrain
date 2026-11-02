from __future__ import annotations

from .base import FeedHealth, FuelProvider


class SaFuelProvider(FuelProvider):
    state = "SA"
    feed_name = "Unavailable"

    _health = FeedHealth(status="pending", last_success=None, last_error=None)

    def is_available(self) -> bool:
        return False

    def fetch_stations(self) -> list[dict]:
        return []

    def get_health(self) -> FeedHealth:
        return self._health