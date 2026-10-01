"""Vehicle domain services."""

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
    "get_accessible_vehicle",
    "get_owned_vehicle",
    "require_ai_vehicle",
    "require_logbook_enabled",
    "sync_odometer_from_fuel",
    "lookup_rego",
    "enforce_vehicle_limit",
    "get_vehicle_timeline",
    "invite_share",
    "list_user_vehicles",
    "list_vehicle_shares",
]