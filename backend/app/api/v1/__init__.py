"""API v1 router aggregation."""

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    analytics,
    auth,
    diagnostics,
    fuel,
    mods,
    parts,
    receipts,
    services,
    valuation,
    vehicles,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(admin.router)
api_router.include_router(vehicles.router)
api_router.include_router(services.router)
api_router.include_router(fuel.router)
api_router.include_router(diagnostics.router)
api_router.include_router(mods.router)
api_router.include_router(receipts.router)
api_router.include_router(parts.router)
api_router.include_router(valuation.router)
api_router.include_router(analytics.router)
