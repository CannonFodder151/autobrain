from __future__ import annotations

from typing import Dict, List

SUPPORTED_STATES = {"WA", "QLD"}
PENDING_STATES = {"NSW", "ACT", "VIC"}
ALL_STATES = ["WA", "QLD", "NSW", "ACT", "VIC"]

FEED_NAMES = {"WA": "WA FuelWatch (official)", "QLD": "FuelPriceQLD (partner)"}

_FEED_HEALTH: Dict[str, dict] = {
    "WA": {"status": "ok", "last_success": None, "last_error": None},
    "QLD": {"status": "ok", "last_success": None, "last_error": None},
}

_STATIONS: Dict[str, List[dict]] = {
    "WA": [
        {"id": "wa-1", "name": "BP Perth CBD", "state": "WA", "suburb": "Perth", "price_cpl": 189.9, "fuel_type": "ULP", "updated_at": "2026-11-01T09:00:00Z"},
        {"id": "wa-2", "name": "Shell Fremantle", "state": "WA", "suburb": "Fremantle", "price_cpl": 187.5, "fuel_type": "ULP", "updated_at": "2026-11-01T09:15:00Z"},
    ],
    "QLD": [
        {"id": "qld-1", "name": "Caltex Brisbane", "state": "QLD", "suburb": "Brisbane", "price_cpl": 192.3, "fuel_type": "ULP", "updated_at": "2026-11-01T08:45:00Z"},
        {"id": "qld-2", "name": "Ampol Gold Coast", "state": "QLD", "suburb": "Gold Coast", "price_cpl": 190.1, "fuel_type": "ULP", "updated_at": "2026-11-01T08:30:00Z"},
    ],
}