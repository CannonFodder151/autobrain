"""Vehicle business logic moved to the vehicles domain module (AUT-3814).

The canonical definitions now live in
:mod:`app.modules.vehicles.services.vehicle`. This module re-exports them so
that existing ``app.services.vehicle`` imports keep working — the functions are
the *same objects*, so ``monkeypatch`` on either path still affects both.

Import from :mod:`app.modules.vehicles.services.vehicle` in new code.
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
