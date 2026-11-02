"""Vehicle Health Score API endpoints."""

from fastapi import APIRouter, HTTPException, Path

from app.schemas.health_score import (
    EngineeringHelperSummary,
    HealthScoreComponent,
    HealthScoreResponse,
    HealthStatus,
    VehicleNotFoundError,
)
from app.services.engineering_helper import (
    VehicleState,
    compute_guidance,
    primary_guidance,
    generate_ai_explanation,
)
from app.services.health_score import (
    VehicleHealthLabel,
    VehicleHealthScoreEngine,
)

router = APIRouter()
_engine = VehicleHealthScoreEngine()


def _label_to_status(label: VehicleHealthLabel) -> HealthStatus:
    return HealthStatus(label.value)


def _mock_vehicle_data(vehicle_id: str) -> dict | None:
    mock_data = {
        "VIN1234567890": {
            "mileage": 45000,
            "components": [
                {"name": "Engine", "score": 88.5, "details": "Oil change due in 2000 miles"},
                {"name": "Transmission", "score": 92.0, "details": "Fluid level optimal"},
                {"name": "Brakes", "score": 75.0, "details": "Front pads at 40%"},
                {"name": "Tires", "score": 82.0, "details": "Tread depth 6/32\""},
                {"name": "Battery", "score": 90.0, "details": "Charge holding well"},
                {"name": "Suspension", "score": 85.0, "details": "No leaks detected"},
            ],
        },
        "VIN0987654321": {
            "mileage": 120000,
            "components": [
                {"name": "Engine", "score": 65.0, "details": "Minor oil leak detected"},
                {"name": "Transmission", "score": 70.0, "details": "Shifting slightly rough"},
                {"name": "Brakes", "score": 45.0, "details": "Rear pads need replacement"},
                {"name": "Tires", "score": 55.0, "details": "Tread depth 3/32\""},
                {"name": "Battery", "score": 60.0, "details": "Charge capacity reduced"},
                {"name": "Suspension", "score": 50.0, "details": "Struts showing wear"},
            ],
        },
    }
    return mock_data.get(vehicle_id)


def _vehicle_state_from_mock(vehicle_id: str, vehicle_data: dict) -> VehicleState:
    """Build a VehicleState from mock data for engineering helper."""
    return VehicleState(
        vehicle_id=vehicle_id,
        engine_light_on=False,
        fault_codes=[],
        rego_expiry="2026-12-01",
        rego_valid=True,
        current_mileage=vehicle_data.get("mileage"),
        last_service_mileage=vehicle_data.get("mileage", 0) - 5000,
        service_interval_km=10000,
        ownership_status="registered",
        fuel_level_pct=60.0,
        is_ev=False,
        is_phev=False,
        battery_soh_pct=None,
        range_km=None,
    )


def _calculate_status(score: float) -> HealthStatus:
    if score >= 90:
        return HealthStatus.EXCELLENT
    elif score >= 75:
        return HealthStatus.GOOD
    elif score >= 60:
        return HealthStatus.FAIR
    elif score >= 40:
        return HealthStatus.POOR
    return HealthStatus.CRITICAL


@router.get(
    "/vehicles/{vehicle_id}/health-score",
    response_model=HealthScoreResponse,
    responses={
        404: {"model": VehicleNotFoundError, "description": "Vehicle not found"},
    },
    summary="Get Vehicle Health Score",
    description="Returns the comprehensive health score for a specific vehicle including component-level breakdown and VASS engineering helper.",
)
async def get_vehicle_health_score(
    vehicle_id: str = Path(..., description="Vehicle ID (VIN)", min_length=1, max_length=50),
) -> HealthScoreResponse:
    vehicle_data = _mock_vehicle_data(vehicle_id)
    if not vehicle_data:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    components = [
        HealthScoreComponent(
            name=comp["name"],
            score=comp["score"],
            status=_calculate_status(comp["score"]),
            details=comp.get("details"),
        )
        for comp in vehicle_data["components"]
    ]

    overall_score = sum(c.score for c in components) / len(components)

    # Compute VASS engineering helper (first thing owner sees on state change)
    vstate = _vehicle_state_from_mock(vehicle_id, vehicle_data)
    guidances = compute_guidance(vstate)
    primary = primary_guidance(guidances)
    ai_result = generate_ai_explanation(vstate, primary, model=None)

    engineering_helper = EngineeringHelperSummary(
        primary_state=primary.state,
        primary_severity=primary.severity,
        primary_title=primary.title,
        primary_message=primary.message,
        ai_explanation=ai_result["explanation"],
        used_fallback=ai_result["used_fallback"],
    )

    return HealthScoreResponse(
        vehicle_id=vehicle_id,
        overall_score=round(overall_score, 1),
        overall_status=_calculate_status(overall_score),
        components=components,
        last_updated="2026-11-01T10:00:00Z",
        mileage=vehicle_data.get("mileage"),
        engineering_helper=engineering_helper,
    )


def _status_from_score(score: float) -> VehicleHealthLabel:
    if score >= 90:
        return VehicleHealthLabel.EXCELLENT
    elif score >= 75:
        return VehicleHealthLabel.GOOD
    elif score >= 60:
        return VehicleHealthLabel.FAIR
    elif score >= 40:
        return VehicleHealthLabel.POOR
    return VehicleHealthLabel.CRITICAL