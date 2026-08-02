"""ORM models. Imported for Alembic autogenerate and app wiring."""

from app.models.user import User
from app.models.vehicle import Vehicle, VehicleEvent
from app.models.service import ServiceRecord, ServiceItem
from app.models.fuel import FuelLog
from app.models.diagnostic import Diagnostic
from app.models.mod import Modification
from app.models.part import Part, PartMovement
from app.models.receipt import Receipt, ExtractedItem
from app.models.valuation import ValuationSnapshot

__all__ = [
    "User",
    "Vehicle",
    "VehicleEvent",
    "ServiceRecord",
    "ServiceItem",
    "FuelLog",
    "Diagnostic",
    "Modification",
    "Part",
    "PartMovement",
    "Receipt",
    "ExtractedItem",
    "ValuationSnapshot",
]
