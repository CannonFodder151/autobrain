"""Resale estimate endpoint.

GET /api/v1/resale/estimate?make=...&model=...&year=...&mileage=...

Deterministic fallback lives in ``app.services.resale`` so the feature works
end-to-end even when the market-data provider is unconfigured.
"""

from fastapi import APIRouter, Query

from app.services.resale import estimate_resale, ResaleEstimate

router = APIRouter(prefix="/resale", tags=["resale"])

@router.get("/estimate", response_model=ResaleEstimate)
async def resale_estimate(
    make: str = Query(...),
    model: str = Query(...),
    year: int = Query(...),
    mileage: int = Query(...),
    current_value: float | None = Query(None),
):
    return estimate_resale(make, model, year, mileage, current_value)
