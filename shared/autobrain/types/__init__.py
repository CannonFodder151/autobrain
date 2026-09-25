"""Shared type aliases and value objects."""

from typing import Any, TypeAlias

Money: TypeAlias = float
OdometerKm: TypeAlias = int
VehicleId: TypeAlias = str
UserId: TypeAlias = str
JsonDict: TypeAlias = dict[str, Any]

__all__ = ["Money", "OdometerKm", "VehicleId", "UserId", "JsonDict"]
