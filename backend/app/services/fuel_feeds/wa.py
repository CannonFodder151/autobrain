from __future__ import annotations

from .base import FeedHealth, FuelProvider


class WaFuelProvider(FuelProvider):
    state = "WA"
    feed_name = "WA FuelWatch (official)"

    _stations = [
        {"id": "wa-1", "name": "BP Perth CBD", "state": "WA", "suburb": "Perth", "price_cpl": 189.9, "fuel_type": "ULP", "updated_at": "2026-11-01T09:00:00Z", "lat": -31.9505, "lng": 115.8605},
        {"id": "wa-2", "name": "Shell Fremantle", "state": "WA", "suburb": "Fremantle", "price_cpl": 187.5, "fuel_type": "ULP", "updated_at": "2026-11-01T09:15:00Z", "lat": -32.0569, "lng": 115.7439},
    ]
    _health = FeedHealth(status="ok", last_success=None, last_error=None)

    def is_available(self) -> bool:
        return True

    def fetch_stations(self) -> list[dict]:
        return [dict(s) for s in self._stations]

    def get_health(self) -> FeedHealth:
        return self._health