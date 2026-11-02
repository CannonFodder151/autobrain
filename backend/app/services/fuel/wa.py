from __future__ import annotations

from typing import Any, Dict

from app.services.fuel.prices import _FEED_HEALTH
from app.services.fuel.scraper import Scraper


class WAProvider(Scraper):
    state = "WA"
    feed_name = "WA FuelWatch (official)"

    def fetch(self) -> Dict[str, Any]:
        return {"state": self.state, "supported": True}

    def health(self) -> Dict[str, Any]:
        return _FEED_HEALTH.get(self.state, {"status": "pending", "last_success": None, "last_error": None})