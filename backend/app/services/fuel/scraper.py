from __future__ import annotations

from typing import Any, Dict


class Scraper:
    """Base interface for fuel price scrapers."""

    def fetch(self) -> Dict[str, Any]:
        raise NotImplementedError

    def health(self) -> Dict[str, Any]:
        raise NotImplementedError