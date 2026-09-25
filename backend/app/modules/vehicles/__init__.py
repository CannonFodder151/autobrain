"""Vehicles domain module.

Public API:
    VehicleService  — high-level vehicle CRUD + sharing + rego lookup
    sync_odometer   — sync odometer (delegated to diagnostics module)
    get_market_data — market pricing lookup (re-export)
    check_ownership — ownership verification (re-export)

Internal layout:
    services.py  — CRUD, timeline, shares, rego persistence
    api.py       — FastAPI router mounting this module's endpoints
    schemas.py   — re-exports from app.schemas.vehicle + shared
    models.py    — re-exports from app.models
"""

from .services import VehicleService
from .api import router as api_router

# Re-exports for backward-compat callers of app.modules.vehicles
def sync_odometer(*args, **kwargs):
    from app.services.odometer import sync_odometer as _fn
    return _fn(*args, **kwargs)

def get_market_data(*args, **kwargs):
    from app.services.market_data import get_market_data as _fn
    return _fn(*args, **kwargs)

def check_ownership(*args, **kwargs):
    from app.services.ownership import check_ownership as _fn
    return _fn(*args, **kwargs)

from . import models, schemas

__all__ = [
    "VehicleService",
    "api_router",
    "sync_odometer",
    "get_market_data",
    "check_ownership",
    "models",
    "schemas",
]
