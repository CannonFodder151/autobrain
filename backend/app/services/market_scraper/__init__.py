"""Market-data scraper package (AUT-4113).

Provides local scraping functions for CarsGuide, BikesGuide, and SCA
that were previously hosted in a separate market-data container.
These are invoked directly by Celery tasks and market_data service.
"""

from .carsguide import search_carsguide
from .bikesguide import search_bikesguide
from .sca import search_sca

__all__ = [
    "search_carsguide",
    "search_bikesguide",
    "search_sca",
]