"""Shared configuration re-export.

Exposes a minimal subset of settings so modules don't need to import from
`app.core.config` directly (which would create a circular dependency if
core ever imports a module).
"""

from __future__ import annotations

from app.core.config import settings

__all__ = ["settings"]