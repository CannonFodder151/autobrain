"""Backwards-compatible re-export for the vehicle domain router.

The real router now lives in ``app.modules.vehicles.api.vehicles``. This shim
keeps ``from app.api.v1 import vehicles`` working in ``app/api/v1/__init__.py``.
"""

from app.modules.vehicles.api.vehicles import router

__all__ = ["router"]