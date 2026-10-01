"""Vehicle domain models."""

from app.modules.vehicles.models.vehicle import (
    Vehicle,
    VehicleEvent,
    PowertrainType,
)

__all__ = ["Vehicle", "VehicleEvent", "PowertrainType"]