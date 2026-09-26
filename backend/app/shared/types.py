"""Shared type aliases for AutoBrain backend.

These are deliberately lightweight — they exist so modules can reference
common types without reaching into each other's packages.
"""

from __future__ import annotations

import uuid
from typing import Any, NewType

# Canonical identifier types used across modules.
UserId = NewType("UserId", str)
VehicleId = NewType("VehicleId", str)
ModificationId = NewType("ModificationId", str)
BookingId = NewType("BookingId", str)


def new_id() -> str:
    """Generate a canonical UUID string identifier."""
    return str(uuid.uuid4())


JSON = Any  # JSON-serialisable value (pydantic-compatible alias)


__all__ = [
    "UserId",
    "VehicleId",
    "ModificationId",
    "BookingId",
    "new_id",
    "JSON",
]