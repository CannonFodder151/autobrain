"""Backwards-compatible re-export for the vehicle domain.

The real implementation now lives in ``app.modules.vehicles.models.vehicle``.
This shim keeps the ~50 existing ``from app.models.vehicle import ...`` call
sites working while the vehicle domain is being split out; it is the seam
where callers can be migrated to the domain module one at a time.
"""

from app.modules.vehicles.models.vehicle import (
    PowertrainType,
    Vehicle,
    VehicleEvent,
)

__all__ = [
    "PowertrainType",
    "Vehicle",
    "VehicleEvent",
]