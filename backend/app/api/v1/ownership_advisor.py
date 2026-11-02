from fastapi import APIRouter, Path

from app.schemas.ownership_advisor import OwnershipAdvisorInput, OwnershipAdvisorResponse, AdvisorResultOut
from app.services.ownership_advisor import AdvisorInput, run_all

router = APIRouter()


@router.post(
    "/vehicles/{vehicle_id}/ownership-advisor",
    response_model=OwnershipAdvisorResponse,
    summary="Run Ownership Advisor for a vehicle",
    description="Deterministic-first six-mode advisor: value, replace, upgrade, finance, dream, ai_advisor.",
)
async def run_ownership_advisor(
    vehicle_id: str = Path(..., min_length=1, max_length=50),
    data: OwnershipAdvisorInput = ...,
) -> OwnershipAdvisorResponse:
    if data.vehicle_id != vehicle_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="vehicle_id in path and body must match")
    inp = AdvisorInput(
        vehicle_id=data.vehicle_id,
        make=data.make,
        model=data.model,
        year=data.year,
        mileage=data.mileage,
        current_value=data.current_value,
        replacement_cost=data.replacement_cost,
        upgrade_budget=data.upgrade_budget,
        interest_rate=data.interest_rate,
        loan_term_months=data.loan_term_months,
        dream_price=data.dream_price,
        dream_monthly_budget=data.dream_monthly_budget,
    )
    results = run_all(inp)
    return OwnershipAdvisorResponse(
        vehicle_id=vehicle_id,
        results=[AdvisorResultOut(mode=r.mode, value=r.value, detail=r.detail, breakdown=r.breakdown) for r in results],
        used_fallback=True,
        ai_explanation=None,
    )