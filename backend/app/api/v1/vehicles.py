"""Vehicle routes moved to the vehicles domain module (AUT-3814).

The canonical routes now live in :mod:`app.modules.vehicles.api.vehicles`.
This module re-exports the router so that ``app.api.v1`` keeps importing
``vehicles.router`` unchanged. It is the *same* APIRouter object, so route
registration and OpenAPI output are identical either way.

Import from :mod:`app.modules.vehicles.api.vehicles` in new code.
"""

from app.modules.vehicles.api.vehicles import router

__all__ = ["router"]
