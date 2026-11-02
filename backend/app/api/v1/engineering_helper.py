from fastapi import APIRouter, HTTPException, Path

from app.schemas.engineering_helper import (
    EngineeringHelperResponse,
    VehicleStateInput,
)
from app.services.engineering_helper import (
    VehicleState,
    compute_guidance,
    primary_guidance,
    to_dict,
    generate_ai_explanation,
)

router = APIRouter()


@router.post(
    "/vehicles/{vehicle_id}/engineering-helper",
    response_model=EngineeringHelperResponse,
    summary="Get VASS engineering guidance",
    description=(
        "State-aware engineering helper. Returns deterministic plain-English "
        "guidance for each vehicle state (engine light, rego, service interval, "
        "ownership, fuel, EV/PHEV powertrain). Always produces an answer; an "
        "AI-assisted explanation is included when an AI model is available."
    ),
)
async def get_engineering_helper(
    vehicle_id: str = Path(..., description="Vehicle ID (VIN)", min_length=1, max_length=50),
    state: VehicleStateInput = ...,
) -> EngineeringHelperResponse:
    if state.vehicle_id != vehicle_id:
        raise HTTPException(status_code=422, detail="vehicle_id in path and body must match")

    vstate = VehicleState(
        vehicle_id=state.vehicle_id,
        engine_light_on=state.engine_light_on,
        fault_codes=state.fault_codes,
        rego_expiry=state.rego_expiry,
        rego_valid=state.rego_valid,
        current_mileage=state.current_mileage,
        last_service_mileage=state.last_service_mileage,
        service_interval_km=state.service_interval_km,
        ownership_status=state.ownership_status,
        fuel_level_pct=state.fuel_level_pct,
        is_ev=state.is_ev,
        is_phev=state.is_phev,
        battery_soh_pct=state.battery_soh_pct,
        range_km=state.range_km,
    )

    guidances = compute_guidance(vstate)
    primary = primary_guidance(guidances)

    ai_result = generate_ai_explanation(vstate, primary, model=None)

    return EngineeringHelperResponse(
        vehicle_id=vehicle_id,
        guidances=[to_dict(g) for g in guidances],
        primary=to_dict(primary),
        ai_explanation=ai_result["explanation"],
        used_fallback=ai_result["used_fallback"],
    )