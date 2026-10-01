"""Vehicle domain — schema layer.

Request/response models for the vehicle API. Imports only from
``app.modules.vehicles.models``; see ``backend/.importlinter``.
"""

from app.modules.vehicles.schemas.vehicle import (
    RegoLookupRequest,
    RegoLookupResponse,
    ShareCreate,
    ShareInviteOut,
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
    "ShareInviteOut",
    "ShareOut",
    "TimelineEventOut",
    "VehicleCreate",
    "VehicleOut",
    "VehicleUpdate",
]