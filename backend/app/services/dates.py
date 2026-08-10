"""Australian financial-year helpers (shared by fuel + logbook routes)."""

from datetime import datetime, timezone


def current_fy() -> int:
    """Australian financial year ends 30 June. fy=2026 covers 2025-07-01..2026-06-30."""
    today = datetime.now(timezone.utc)
    return today.year + (1 if today.month >= 7 else 0)


def fy_bounds(fy: int) -> tuple[datetime, datetime]:
    start = datetime(fy - 1, 7, 1, tzinfo=timezone.utc)
    end = datetime(fy, 6, 30, 23, 59, 59, tzinfo=timezone.utc)
    return start, end
