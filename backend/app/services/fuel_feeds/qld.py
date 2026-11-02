from __future__ import annotations

from .base import FeedHealth, FuelProvider


class QldFuelProvider(FuelProvider):
    state = "QLD"
    feed_name = "FuelPriceQLD (partner)"

    _stations = [
        {"id": "qld-1", "name": "Caltex Brisbane", "state": "QLD", "suburb": "Brisbane", "price_cpl": 192.3, "fuel_type": "ULP", "updated_at": "2026-11-01T08:45:00Z", "lat": -27.4698, "lng": 153.0251},
        {"id": "qld-2", "name": "Ampol Gold Coast", "state": "QLD", "suburb": "Gold Coast", "price_cpl": 190.1, "fuel_type": "ULP", "updated_at": "2026-11-01T08:30:00Z", "lat": -28.0167, "lng": 153.4000},
    ]
    _health = FeedHealth(status="ok", last_success=None, last_error=None)

    def is_available(self) -> bool:
        return True

    def fetch_stations(self) -> list[dict]:
        return [dict(s) for s in self._stations]

    def get_health(self) -> FeedHealth:
        return self._health