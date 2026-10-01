"""Backwards-compatible re-export for the vehicle domain.

The real implementation now lives in ``app.modules.vehicles.services.rego``.
See ``app/models/vehicle.py`` for the rationale behind these shims.
"""

from app.modules.vehicles.services.rego import lookup_rego

__all__ = ["lookup_rego"]
