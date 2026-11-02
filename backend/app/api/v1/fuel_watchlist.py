from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.fuel_feeds import get_stations, fetch_state

router = APIRouter()

_WATCHES: Dict[str, dict] = {}
_NOTIFICATIONS: Dict[str, List[dict]] = {}


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def run_check_all_users() -> None:
    users = {w.get("user_id", "default-user") for w in _WATCHES.values() if w.get("active")}
    for uid in users:
        try:
            await check_alerts(user_id=uid)
        except Exception:
            pass


class FuelWatchIn(BaseModel):
    user_id: str = Field(default="default-user")
    station_id: str
    station_name: Optional[str] = None
    state: str
    fuel_type: str = "ULP"
    threshold_pct: float = Field(default=5.0, ge=0.1, le=100.0)


class FuelWatch(FuelWatchIn):
    id: str
    active: bool = True
    last_price: Optional[float] = None
    created_at: str


class FuelWatchPatch(BaseModel):
    fuel_type: Optional[str] = None
    threshold_pct: Optional[float] = Field(default=None, ge=0.1, le=100.0)
    active: Optional[bool] = None


class FuelAlert(BaseModel):
    watch_id: str
    user_id: str
    station_id: str
    station_name: Optional[str] = None
    state: str
    fuel_type: str
    previous_price: Optional[float] = None
    current_price: float
    change_pct: float
    direction: str  # "up" | "down"
    threshold_pct: float
    notified: bool = True
    created_at: str


@router.post("/fuel-watchlist", response_model=FuelWatch)
async def create_watch(body: FuelWatchIn):
    # Resolve station name from feed if not provided
    name = body.station_name
    if not name:
        for s in get_stations(body.state.upper()):
            if s.get("id") == body.station_id:
                name = s.get("name")
                break
    rec = {
        "id": _id(),
        "user_id": body.user_id,
        "station_id": body.station_id,
        "station_name": name,
        "state": body.state.upper(),
        "fuel_type": body.fuel_type,
        "threshold_pct": body.threshold_pct,
        "active": True,
        "last_price": None,
        "created_at": _now(),
    }
    _WATCHES[rec["id"]] = rec
    return rec


@router.get("/fuel-watchlist", response_model=List[FuelWatch])
async def list_watches(user_id: str = Query(default="default-user")):
    return [w for w in _WATCHES.values() if w["user_id"] == user_id]


@router.patch("/fuel-watchlist/{watch_id}", response_model=FuelWatch)
async def patch_watch(watch_id: str, body: FuelWatchPatch):
    if watch_id not in _WATCHES:
        raise HTTPException(404, "Watch not found")
    w = _WATCHES[watch_id]
    if body.fuel_type is not None:
        w["fuel_type"] = body.fuel_type
    if body.threshold_pct is not None:
        w["threshold_pct"] = body.threshold_pct
    if body.active is not None:
        w["active"] = body.active
    return w


@router.delete("/fuel-watchlist/{watch_id}")
async def delete_watch(watch_id: str):
    if watch_id not in _WATCHES:
        raise HTTPException(404, "Watch not found")
    del _WATCHES[watch_id]
    return {"deleted": watch_id}


def _station_price(state: str, station_id: str, fuel_type: str) -> Optional[float]:
    res = fetch_state(state)
    if not res.get("available"):
        return None
    for s in res.get("stations", []):
        if s.get("id") == station_id:
            if fuel_type and s.get("fuel_type") and s.get("fuel_type") != fuel_type:
                continue
            return s.get("price_cpl")
    # fallback: any matching station id
    for s in res.get("stations", []):
        if s.get("id") == station_id:
            return s.get("price_cpl")
    return None


@router.post("/fuel-watchlist/check-alerts", response_model=List[FuelAlert])
async def check_alerts(user_id: str = Query(default="default-user")):
    triggered: List[dict] = []
    for w in list(_WATCHES.values()):
        if w["user_id"] != user_id or not w.get("active"):
            continue
        price = _station_price(w["state"], w["station_id"], w["fuel_type"])
        if price is None:
            continue
        prev = w.get("last_price")
        w["last_price"] = price
        if prev is None:
            continue
        if prev == 0:
            continue
        change_pct = (price - prev) / prev * 100.0
        if abs(change_pct) >= w["threshold_pct"]:
            direction = "up" if change_pct >= 0 else "down"
            alert = {
                "watch_id": w["id"],
                "user_id": w["user_id"],
                "station_id": w["station_id"],
                "station_name": w.get("station_name"),
                "state": w["state"],
                "fuel_type": w["fuel_type"],
                "previous_price": prev,
                "current_price": price,
                "change_pct": round(change_pct, 2),
                "direction": direction,
                "threshold_pct": w["threshold_pct"],
                "notified": True,
                "created_at": _now(),
            }
            triggered.append(alert)
            _NOTIFICATIONS.setdefault(w["user_id"], []).append(alert)
    return triggered


@router.get("/fuel-watchlist/notifications", response_model=List[FuelAlert])
async def list_notifications(user_id: str = Query(default="default-user")):
    return _NOTIFICATIONS.get(user_id, [])
