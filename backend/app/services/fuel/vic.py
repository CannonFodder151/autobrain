from __future__ import annotations

from typing import Any, Dict

from app.services.fuel.scraper import Scraper


class VICProvider(Scraper):
    state = "VIC"
    feed_name = "Unavailable"
    supported = False

    def fetch(self) -> Dict[str, Any]:
        return {"state": self.state, "supported": False}

    def health(self) -> Dict[str, Any]:
        return {"status": "pending", "last_success": None, "last_error": None}