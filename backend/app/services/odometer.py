"""Backwards-compatible re-export for the vehicle domain.

The real implementation now lives in ``app.modules.vehicles.services.odometer``.
See ``app/models/vehicle.py`` for the rationale behind these shims.
"""

from app.modules.vehicles.services.odometer import (
    suggest_due_service,
    sync_odometer,
)

__all__ = ["suggest_due_service", "sync_odometer"]
