from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import List, Optional
import uuid, datetime

router = APIRouter()
_STORE: List[dict] = []

class ReminderIn(BaseModel):
    vehicleId: str
    kind: str
    dueDate: str
    message: Optional[str] = None

class ReminderOut(ReminderIn):
    id: str
    createdAt: str

@router.post("", response_model=ReminderOut)
async def create_reminder(body: ReminderIn):
    rec = {"id": str(uuid.uuid4()), "createdAt": datetime.datetime.utcnow().isoformat(), **body.model_dump()}
    _STORE.append(rec)
    return ReminderOut(**rec)

@router.get("", response_model=List[ReminderOut])
async def list_reminders(vehicleId: Optional[str] = Query(None)):
    items = _STORE if vehicleId is None else [r for r in _STORE if r["vehicleId"] == vehicleId]
    return [ReminderOut(**r) for r in items]
