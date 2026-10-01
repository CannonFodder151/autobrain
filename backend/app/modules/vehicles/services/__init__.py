"""Vehicle domain — service layer.

Business logic for vehicles: ownership/entitlement checks, odometer
reconciliation, rego lookup and the vehicle timeline. Imports from
``models`` and ``schemas`` only; see ``backend/.importlinter``.
"""

from app.modules.vehicles.services.odometer import sync_odometer
from app.modules.vehicles.services.ownership import (
    clear_primary,
    effective_feature_owner,
    get_accessible_vehicle,
    get_owned_vehicle,
    require_ai_vehicle,
    require_logbook_enabled,
    sync_odometer_from_fuel,
)
from app.modules.vehicles.services.rego import lookup_rego
from app.modules.vehicles.services.vehicle import (
    enforce_vehicle_limit,
    get_vehicle_timeline,
    invite_share,
    list_user_vehicles,
    list_vehicle_shares,
)

__all__ = [
    "clear_primary",
    "effective_feature_owner",
    "enforce_vehicle_limit",
    "get_accessible_vehicle",
    "get_owned_vehicle",
    "get_vehicle_timeline",
    "invite_share",
    "list_user_vehicles",
    "list_vehicle_shares",
    "lookup_rego",
    "require_ai_vehicle",
    "require_logbook_enabled",
    "sync_odometer",
    "sync_odometer_from_fuel",
]