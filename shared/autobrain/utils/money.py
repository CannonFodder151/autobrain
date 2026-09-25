"""Currency helpers."""

from __future__ import annotations

from .types import Money


def format_money(amount: Money | None, currency: str = "AUD") -> str | None:
    """Render a money value without locale drift between backend and AI."""
    if amount is None:
        return None
    return f"{currency} {amount:,.2f}"
