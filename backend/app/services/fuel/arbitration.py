from __future__ import annotations

from datetime import datetime, timezone

from app.services.fuel.prices import _FEED_HEALTH


def mark_feed_down(state: str, error: str) -> None:
    if state in _FEED_HEALTH:
        _FEED_HEALTH[state]["status"] = "down"
        _FEED_HEALTH[state]["last_error"] = error


def mark_feed_ok(state: str) -> None:
    if state in _FEED_HEALTH:
        _FEED_HEALTH[state]["status"] = "ok"
        _FEED_HEALTH[state]["last_success"] = datetime.now(timezone.utc).isoformat()
        _FEED_HEALTH[state]["last_error"] = None