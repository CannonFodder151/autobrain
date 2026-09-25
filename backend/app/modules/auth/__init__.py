"""Authentication and authorization module contract.

This module defines the public interface for authentication dependencies.
Actual implementations live in:
- app.api.deps (FastAPI dependencies)
- app.services.auth (business logic)
- app.core.security (token encoding/decoding)

Use TYPE_CHECKING for type hints without runtime imports.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.device import Device
    from fastapi import Request, WebSocket

__all__ = [
    # FastAPI dependencies (from app.api.deps)
    "get_current_user",
    "require_admin",
    "require_write",
    "require_ai",
    "require_premium",
    "require_premium_write",
    "require_rego",
    "verify_dongle_server",
    "get_device_from_key",
    "get_ha_user",
    "authenticate_ws",
    # Business logic (from app.services.auth)
    "create_access_token",
    "create_refresh_token",
]

# --- Re-exports (lazy, no top-level side effects) ---

def __getattr__(name: str):
    """Lazy import to avoid circular dependencies and config requirements at import time."""
    if name in {
        "get_current_user", "require_admin", "require_write", "require_ai",
        "require_premium", "require_premium_write", "require_rego",
        "verify_dongle_server", "get_device_from_key", "get_ha_user",
        "authenticate_ws",
    }:
        from app.api.deps import (
            get_current_user, require_admin, require_write, require_ai,
            require_premium, require_premium_write, require_rego,
            verify_dongle_server, get_device_from_key, get_ha_user,
            authenticate_ws,
        )
        globals().update({
            "get_current_user": get_current_user,
            "require_admin": require_admin,
            "require_write": require_write,
            "require_ai": require_ai,
            "require_premium": require_premium,
            "require_premium_write": require_premium_write,
            "require_rego": require_rego,
            "verify_dongle_server": verify_dongle_server,
            "get_device_from_key": get_device_from_key,
            "get_ha_user": get_ha_user,
            "authenticate_ws": authenticate_ws,
        })
        return globals()[name]

    if name in {"create_access_token", "create_refresh_token"}:
        from app.services.auth import create_access_token, create_refresh_token
        globals()["create_access_token"] = create_access_token
        globals()["create_refresh_token"] = create_refresh_token
        return globals()[name]

    raise AttributeError(f"module 'app.modules.auth' has no attribute '{name}'")