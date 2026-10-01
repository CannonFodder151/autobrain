"""Backwards-compatible re-export for the vehicle domain.

The real implementation now lives in ``app.modules.vehicles.services.vehicle``.
See ``app/models/vehicle.py`` for the rationale behind these shims.
"""

from app.modules.vehicles.services.vehicle import (
    enforce_vehicle_limit,
    get_vehicle_timeline,
    invite_share,
    list_user_vehicles,
    list_vehicle_shares,
)

__all__ = [
    "enforce_vehicle_limit",
    "get_vehicle_timeline",
    "invite_share",
    "list_user_vehicles",
    "list_vehicle_shares",
]
