"""API v1 router aggregation."""

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    admin_api,
    advisor,
    analytics,
    auth,
    billing,
    ci,
    devices,
    diagnostics,
    dongle_firmware,
    electricity,
    fuel,
    fuel_prices,
    fuel_servo,
    issues,
    logbook,
    mods,
    notifications,
    obd,
    parts,
    receipts,
    search,
    services,
    shares,
    social,
    valuation,
    vehicles,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(billing.router)
api_router.include_router(admin.router)
api_router.include_router(admin.admin_ops)
api_router.include_router(admin_api.router)
api_router.include_router(vehicles.router)
api_router.include_router(shares.router)
api_router.include_router(services.router)
api_router.include_router(fuel.router)
api_router.include_router(electricity.router)
api_router.include_router(fuel_servo.router)
api_router.include_router(fuel_prices.router)
api_router.include_router(diagnostics.router)
api_router.include_router(logbook.router)
api_router.include_router(obd.router)
api_router.include_router(mods.router)
api_router.include_router(receipts.router)
api_router.include_router(parts.router)
api_router.include_router(valuation.router)
api_router.include_router(advisor.router)
api_router.include_router(analytics.router)
api_router.include_router(notifications.router)
api_router.include_router(devices.router)
api_router.include_router(dongle_firmware.router)
api_router.include_router(search.router)
api_router.include_router(social.router)
api_router.include_router(issues.router)
api_router.include_router(ci.router)
