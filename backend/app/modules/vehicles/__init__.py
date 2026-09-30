"""Vehicles domain module.

This module contains all vehicle-related code organized by layer:
- models: SQLAlchemy models (Vehicle, VehicleEvent, PowertrainType)
- schemas: Pydantic schemas for API contracts
- services: Business logic (ownership, rego lookup, odometer sync, timeline)
- api: FastAPI routes
"""

from app.modules.vehicles.models import Vehicle, VehicleEvent, PowertrainType
from app.modules.vehicles.schemas import (
    RegoLookupRequest,
    RegoLookupResponse,
    ShareCreate,
    ShareOut,
    ShareInviteOut,
    TimelineEventOut,
    VehicleCreate,
    VehicleOut,
    VehicleUpdate,
)
from app.modules.vehicles.services import (
    clear_primary,
    effective_feature_owner,
    get_accessible_vehicle,
    get_owned_vehicle,
    require_ai_vehicle,
    require_logbook_enabled,
    sync_odometer_from_fuel,
    lookup_rego,
    enforce_vehicle_limit,
    get_vehicle_timeline,
    invite_share,
    list_user_vehicles,
    list_vehicle_shares,
)

__all__ = [
    # Models
    "Vehicle",
    "VehicleEvent",
    "PowertrainType",
    # Schemas
    "RegoLookupRequest",
    "RegoLookupResponse",
    "ShareCreate",
    "ShareOut",
    "ShareInviteOut",
    "TimelineEventOut",
    "VehicleCreate",
    "VehicleOut",
    "VehicleUpdate",
    # Services
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
