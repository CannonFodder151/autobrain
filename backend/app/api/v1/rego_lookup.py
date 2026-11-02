from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from app.services.rego_lookup import lookup_rego, RegoInfo

router = APIRouter()

class RegoOut(BaseModel):
    rego: str
    state: str
    vin: str | None = None
    body: str | None = None
    colour: str | None = None
    status: str
    make: str | None = None
    model: str | None = None
    year: int | None = None
    errors: list[str] = []

@router.get("/lookup", response_model=RegoOut)
async def rego_lookup(rego: str = Query(...), state: str = Query("NSW")):
    info = lookup_rego(rego, state)
    return RegoOut(**info.__dict__)
