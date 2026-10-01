"""Route-parity guard for the vehicles domain module split (AUT-3814).

Importing the app exercises every router; the assert catches a refactor that
silently drops or renames an endpoint. Run directly:

    python3 backend/tests/test_vehicles_module_split.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import conftest  # noqa: E402,F401  (sets required env before app import)

from app.main import app  # noqa: E402

# Endpoints owned by the vehicles domain module (app/modules/vehicles/api).
VEHICLE_ROUTES = {
    ("GET", "/api/v1/vehicles"),
    ("POST", "/api/v1/vehicles"),
    ("GET", "/api/v1/vehicles/rego-lookup"),
    ("GET", "/api/v1/vehicles/{vehicle_id}"),
    ("PATCH", "/api/v1/vehicles/{vehicle_id}"),
    ("DELETE", "/api/v1/vehicles/{vehicle_id}"),
    ("GET", "/api/v1/vehicles/{vehicle_id}/timeline"),
    ("POST", "/api/v1/vehicles/{vehicle_id}/shares"),
    ("GET", "/api/v1/vehicles/{vehicle_id}/shares"),
}


def test_vehicles_endpoints_registered() -> None:
    registered = {
        (m, r.path)
        for r in app.routes
        for m in getattr(r, "methods", set()) or set()
    }
    missing = VEHICLE_ROUTES - registered
    assert not missing, f"vehicles module dropped endpoints: {sorted(missing)}"


def test_shims_are_the_same_objects() -> None:
    """The legacy import paths must be aliases, not copies.

    Copies would mean a monkeypatch on one path silently misses the other.
    """
    from app.api.v1.vehicles import router as shim_router
    from app.models.vehicle import Vehicle as ShimVehicle
    from app.modules.vehicles.api.vehicles import router as canonical_router
    from app.modules.vehicles.models.vehicle import Vehicle

    assert shim_router is canonical_router
    assert ShimVehicle is Vehicle


if __name__ == "__main__":
    test_vehicles_endpoints_registered()
    test_shims_are_the_same_objects()
    print("ok: vehicles module split — endpoints registered, shims aliased")
