"""Vehicle models — re-export the canonical SQLAlchemy models.

Re-exporting keeps the module self-contained so callers import
``app.modules.vehicles.models`` instead of reaching into ``app.models``
directly.
"""

from app.models.vehicle import Vehicle, VehicleEvent
from app.models.share import VehicleShare

__all__ = ["Vehicle", "VehicleEvent", "VehicleShare"]
