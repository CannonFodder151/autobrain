"""Backwards-compatible re-export for the vehicle domain.

The real implementation now lives in
``app.modules.vehicles.services.ownership``. See ``app/models/vehicle.py`` for
the rationale behind these shims.
"""

from app.modules.vehicles.services.ownership import (
    clear_primary,
    effective_feature_owner,
    get_accessible_vehicle,
    get_owned_vehicle,
    require_ai_vehicle,
    require_logbook_enabled,
    sync_odometer_from_fuel,
)

__all__ = [
    "clear_primary",
    "effective_feature_owner",
    "get_accessible_vehicle",
    "get_owned_vehicle",
    "require_ai_vehicle",
    "require_logbook_enabled",
    "sync_odometer_from_fuel",
]
