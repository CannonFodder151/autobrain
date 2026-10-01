"""Vehicle models moved to the vehicles domain module (AUT-3814).

The canonical definitions now live in
:mod:`app.modules.vehicles.models.vehicle`. This module re-exports them so
that existing ``app.models.vehicle`` imports keep working; the model classes
are the *same objects*, so Alembic and the SQLAlchemy registry are unaffected.

Import from :mod:`app.modules.vehicles.models.vehicle` in new code.
"""

from app.modules.vehicles.models.vehicle import PowertrainType, Vehicle, VehicleEvent

__all__ = ["PowertrainType", "Vehicle", "VehicleEvent"]
