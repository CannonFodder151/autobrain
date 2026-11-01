from fastapi import APIRouter, HTTPException, Path
from app.schemas.health_score import (
    HealthScoreResponse,
    HealthScoreComponent,
    HealthStatus,
    VehicleNotFoundError,
)

router = APIRouter()


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


@router.get(
    "/vehicles/{vehicle_id}/health-score",
    response_model=HealthScoreResponse,
    responses={
        404: {"model": VehicleNotFoundError, "description": "Vehicle not found"},
    },
    summary="Get Vehicle Health Score",
    description="Returns the comprehensive health score for a specific vehicle including component-level breakdown.",
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

    return HealthScoreResponse(
        vehicle_id=vehicle_id,
        overall_score=round(overall_score, 1),
        overall_status=_calculate_status(overall_score),
        components=components,
        last_updated="2026-11-01T10:00:00Z",
        mileage=vehicle_data.get("mileage"),
    )