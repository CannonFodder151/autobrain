"""Shared helpers and constants used across Ownership Advisor sub-modules."""

from __future__ import annotations


# Currency. AutoBrain is AU-only; one source of truth here keeps the
# response shape consistent.
CURRENCY = "AUD"

# Hard floor / ceiling for any computed value. Stops a junk input from
# emitting a $0 or $1B result on the screen.
_MIN_VALUE = 500.0
_MAX_VALUE = 5_000_000.0


def _safe(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return max(_MIN_VALUE, min(_MAX_VALUE, f))