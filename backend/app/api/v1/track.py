from __future__ import annotations

import statistics
import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()

# In-memory stores
_CARS: Dict[str, dict] = {}
_SESSIONS: Dict[str, dict] = {}
_LAPS: Dict[str, List[dict]] = {}
_PREP: Dict[str, dict] = {}
_SERVICE: Dict[str, List[dict]] = {}


def _id() -> str:
    return str(uuid.uuid4())


# Schemas
class TrackCarProfileIn(BaseModel):
    baseVehicleId: str
    trackOnly: bool = True
    carClass: Optional[str] = None
    weight: Optional[float] = None
    power: Optional[float] = None
    tyreSpec: Optional[str] = None


class TrackCarProfile(TrackCarProfileIn):
    id: str


class TrackDaySessionIn(BaseModel):
    carId: str
    trackId: str
    date: str
    weather: Optional[str] = None
    driverId: Optional[str] = None
    notes: Optional[str] = None


class TrackDaySession(TrackDaySessionIn):
    id: str


class TrackDaySessionPatch(BaseModel):
    trackId: Optional[str] = None
    date: Optional[str] = None
    weather: Optional[str] = None
    driverId: Optional[str] = None
    notes: Optional[str] = None


class LapIn(BaseModel):
    number: int
    timeMs: int
    sectors: List[int] = Field(default_factory=list)
    fuelUsed: Optional[float] = None
    tyrePressures: List[float] = Field(default_factory=list)
    brakeTemps: List[float] = Field(default_factory=list)


class Lap(LapIn):
    id: str
    sessionId: str


class PrepItem(BaseModel):
    key: str
    done: bool = False
    note: Optional[str] = None


class PrepChecklistIn(BaseModel):
    items: List[PrepItem] = Field(default_factory=list)


class PrepChecklist(PrepChecklistIn):
    id: str
    sessionId: str
    completedAt: Optional[str] = None


class PrepPatch(BaseModel):
    items: Optional[List[PrepItem]] = None
    completedAt: Optional[str] = None


class ServiceEventIn(BaseModel):
    kind: str
    mileageOrHours: Optional[float] = None
    trackHours: Optional[float] = None
    dueAt: Optional[str] = None
    done: bool = False


class ServiceEvent(ServiceEventIn):
    id: str
    carId: str


# Endpoints
@router.post("/cars", response_model=TrackCarProfile)
async def create_car(body: TrackCarProfileIn):
    rec = {"id": _id(), **body.model_dump()}
    _CARS[rec["id"]] = rec
    return rec


@router.get("/cars/{car_id}", response_model=TrackCarProfile)
async def get_car(car_id: str):
    if car_id not in _CARS:
        raise HTTPException(404, "Car not found")
    return _CARS[car_id]


@router.post("/sessions", response_model=TrackDaySession)
async def create_session(body: TrackDaySessionIn):
    if body.carId not in _CARS:
        raise HTTPException(404, "Car not found")
    rec = {"id": _id(), **body.model_dump()}
    _SESSIONS[rec["id"]] = rec
    _LAPS[rec["id"]] = []
    return rec


@router.get("/sessions/{session_id}", response_model=TrackDaySession)
async def get_session(session_id: str):
    if session_id not in _SESSIONS:
        raise HTTPException(404, "Session not found")
    return _SESSIONS[session_id]


@router.patch("/sessions/{session_id}", response_model=TrackDaySession)
async def patch_session(session_id: str, body: TrackDaySessionPatch):
    if session_id not in _SESSIONS:
        raise HTTPException(404, "Session not found")
    rec = _SESSIONS[session_id]
    for k, v in body.model_dump(exclude_none=True).items():
        rec[k] = v
    return rec


@router.post("/sessions/{session_id}/laps", response_model=Lap)
async def add_lap(session_id: str, body: LapIn):
    if session_id not in _SESSIONS:
        raise HTTPException(404, "Session not found")
    rec = {"id": _id(), "sessionId": session_id, **body.model_dump()}
    _LAPS[session_id].append(rec)
    return rec


@router.post("/sessions/{session_id}/prep", response_model=PrepChecklist)
async def create_prep(session_id: str, body: PrepChecklistIn):
    if session_id not in _SESSIONS:
        raise HTTPException(404, "Session not found")
    rec = {"id": _id(), "sessionId": session_id, "items": [i.model_dump() for i in body.items], "completedAt": None}
    _PREP[session_id] = rec
    return rec


@router.patch("/sessions/{session_id}/prep", response_model=PrepChecklist)
async def patch_prep(session_id: str, body: PrepPatch):
    if session_id not in _PREP:
        raise HTTPException(404, "Prep not found")
    rec = _PREP[session_id]
    if body.items is not None:
        rec["items"] = [i.model_dump() for i in body.items]
    if body.completedAt is not None:
        rec["completedAt"] = body.completedAt
    return rec


@router.post("/cars/{car_id}/service", response_model=ServiceEvent)
async def add_service(car_id: str, body: ServiceEventIn):
    if car_id not in _CARS:
        raise HTTPException(404, "Car not found")
    rec = {"id": _id(), "carId": car_id, **body.model_dump()}
    _SERVICE.setdefault(car_id, []).append(rec)
    return rec


@router.get("/cars/{car_id}/service", response_model=List[ServiceEvent])
async def list_service(car_id: str):
    if car_id not in _CARS:
        raise HTTPException(404, "Car not found")
    return _SERVICE.get(car_id, [])


@router.get("/drivers/{driver_id}/stats")
async def driver_stats(driver_id: str):
    sessions = [s for s in _SESSIONS.values() if s.get("driverId") == driver_id]
    lap_times: List[int] = []
    for s in sessions:
        for l in _LAPS.get(s["id"], []):
            lap_times.append(l["timeMs"])
    if not lap_times:
        return {"driverId": driver_id, "bestLap": None, "avgLap": None, "consistency": None, "sessionsCount": len(sessions)}
    avg = statistics.fmean(lap_times)
    consistency = statistics.pstdev(lap_times) if len(lap_times) > 1 else 0.0
    return {
        "driverId": driver_id,
        "bestLap": min(lap_times),
        "avgLap": avg,
        "consistency": consistency,
        "sessionsCount": len(sessions),
    }
