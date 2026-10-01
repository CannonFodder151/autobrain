"""Rego lookup moved to the vehicles domain module (AUT-3814).

The canonical implementation now lives in
:mod:`app.modules.vehicles.services.rego`. This module re-exports it so that
existing ``app.services.rego`` imports keep working.

``httpx`` is re-exported too: tests monkeypatch ``rego.httpx.AsyncClient``
(see tests/test_aut324_rego_log_redaction.py) and that must keep hitting the
module the lookup actually calls.

Import from :mod:`app.modules.vehicles.services.rego` in new code.
"""

from app.modules.vehicles.services import rego as _rego
from app.modules.vehicles.services.rego import KNOWN_STATES, lookup_rego

# Same module object the lookup uses, so patching httpx here patches it there.
httpx = _rego.httpx

__all__ = ["KNOWN_STATES", "lookup_rego", "httpx"]
