"""Vehicle schemas — re-export from the canonical schema layer.

Kept thin so the module boundary is explicit: everything a consumer of the
vehicles module needs lives under ``app.modules.vehicles``.
"""

from app.schemas.vehicle import (
    RegoLookupRequest,
    RegoLookupResponse,
    ShareCreate,
    ShareOut,
    TimelineEventOut,
    VehicleCreate,
    VehicleOut,
    VehicleUpdate,
)

__all__ = [
    "RegoLookupRequest",
    "RegoLookupResponse",
    "ShareCreate",
    "ShareOut",
    "TimelineEventOut",
    "VehicleCreate",
    "VehicleOut",
    "VehicleUpdate",
]
