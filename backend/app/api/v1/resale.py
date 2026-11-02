from fastapi import APIRouter, Query
from pydantic import BaseModel
from app.services.resale import estimate_resale

router = APIRouter()

class ResaleOut(BaseModel):
    make: str
    model: str
    year: int
    mileage: int
    estimated_value: float
    trade_in: float
    depreciation_rate: float
    notes: str = ""

@router.get("/estimate", response_model=ResaleOut)
async def resale_estimate(make: str = Query(...), model: str = Query(...), year: int = Query(...),
                          mileage: int = Query(...), current_value: float | None = Query(None)):
    r = estimate_resale(make, model, year, mileage, current_value)
    return ResaleOut(**r.__dict__)
