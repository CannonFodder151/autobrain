"""Vehicle domain — API adapter layer.

FastAPI router for vehicle CRUD, rego lookup and the timeline. This is the
module's outermost layer: it may import from ``models``, ``schemas`` and
``services``, and nothing inside those layers may import back into it.
"""

from app.modules.vehicles.api.vehicles import router

__all__ = ["router"]