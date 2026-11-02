from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from app.services.fuel.prices import (
    SUPPORTED_STATES,
    PENDING_STATES,
    ALL_STATES,
    FEED_NAMES,
    _FEED_HEALTH,
    _STATIONS,
)


def _freshness_minutes(updated_at: str) -> Optional[int]:
    try:
        dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return int((now - dt).total_seconds() / 60)
    except Exception:
        return None


def get_feed_health(state: str) -> dict:
    fh = _FEED_HEALTH.get(state, {"status": "pending", "last_success": None, "last_error": None})
    return {
        "state": state,
        "feed": FEED_NAMES.get(state, "Unavailable"),
        "status": fh["status"],
        "last_success": fh["last_success"],
        "last_error": fh["last_error"],
    }


def get_stations(state: str) -> List[dict]:
    return _STATIONS.get(state, [])


def fetch_state(state: str) -> dict:
    if state in PENDING_STATES:
        return {
            "state": state,
            "available": False,
            "message": f"Fuel prices for {state} are not available yet. Partner-feed keys pending.",
            "stations": [],
            "feed_status": get_feed_health(state),
        }
    if state not in SUPPORTED_STATES:
        return {
            "state": state,
            "available": False,
            "message": f"Unknown state: {state}.",
            "stations": [],
            "feed_status": None,
        }
    fh = _FEED_HEALTH.get(state, {})
    if fh.get("status") == "down":
        return {
            "state": state,
            "available": False,
            "message": f"Feed for {state} is currently down. Last error: {fh.get('last_error') or 'unknown'}.",
            "stations": [],
            "feed_status": get_feed_health(state),
        }
    stations = []
    for s in get_stations(state):
        s2 = dict(s)
        s2["freshness_minutes"] = _freshness_minutes(s.get("updated_at", ""))
        stations.append(s2)
    return {
        "state": state,
        "available": True,
        "message": None,
        "stations": stations,
        "feed_status": get_feed_health(state),
    }


def all_feed_health() -> List[dict]:
    out = []
    for st in ALL_STATES:
        if st in SUPPORTED_STATES:
            out.append(get_feed_health(st))
        else:
            out.append({
                "state": st,
                "feed": "Unavailable",
                "status": "pending",
                "last_success": None,
                "last_error": None,
            })
    return out


def mark_feed_down(state: str, error: str) -> None:
    if state in _FEED_HEALTH:
        _FEED_HEALTH[state]["status"] = "down"
        _FEED_HEALTH[state]["last_error"] = error


def mark_feed_ok(state: str) -> None:
    if state in _FEED_HEALTH:
        _FEED_HEALTH[state]["status"] = "ok"
        _FEED_HEALTH[state]["last_success"] = datetime.now(timezone.utc).isoformat()
        _FEED_HEALTH[state]["last_error"] = None
