"""Vehicle domain — persistence layer.

Owns the ``Vehicle`` / ``VehicleEvent`` ORM models. This layer must not import
from ``schemas``, ``services`` or ``api``; see ``backend/.importlinter``.
"""

from app.modules.vehicles.models.vehicle import (
    PowertrainType,
    Vehicle,
    VehicleEvent,
)

__all__ = [
    "PowertrainType",
    "Vehicle",
    "VehicleEvent",
]