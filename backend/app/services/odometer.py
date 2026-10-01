"""Odometer sync moved to the vehicles domain module (AUT-3814).

The canonical definitions now live in
:mod:`app.modules.vehicles.services.odometer`. This module re-exports them so
that existing ``app.services.odometer`` imports keep working — the functions
are the *same objects*, so ``monkeypatch`` on either path still affects both.

Import from :mod:`app.modules.vehicles.services.odometer` in new code.
"""

from app.modules.vehicles.services.odometer import suggest_due_service, sync_odometer

__all__ = ["suggest_due_service", "sync_odometer"]
