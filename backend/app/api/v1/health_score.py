"""Vehicle Health Score API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_ai
from app.db.session import get_db
from app.models.user import User
from app.schemas.health_score import HealthScoreResponse
from app.services.health_score import compute_health_score
from app.services.ownership import get_accessible_vehicle, require_ai_vehicle

router = APIRouter(prefix="/vehicles/{vehicle_id}/health-score", tags=["health-score"])


@router.get("", response_model=HealthScoreResponse)
async def get_health_score(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    _: User = Depends(require_ai),
) -> HealthScoreResponse:
    """Get Vehicle Health Score (0-100) with breakdown and predictive alerts."""
    vehicle = await get_accessible_vehicle(db, vehicle_id, user)
    await require_ai_vehicle(db, vehicle, user)

    result = await compute_health_score(db, vehicle)

    # Transform to match schema
    breakdown = result.get("breakdown", {})
    score_breakdown = {
        "diagnostics": float(breakdown.get("diagnostics", {}).get("score", 0)),
        "maintenance": float(breakdown.get("maintenance", {}).get("score", 0)),
        "fuel_efficiency": float(breakdown.get("fuel_efficiency", {}).get("score", 0)),
        "obd_codes": float(breakdown.get("obd_codes", {}).get("score", 0)),
        "parts": float(breakdown.get("parts_wear", {}).get("score", 0)),
    }

    alerts = []
    for a in result.get("alerts", []):
        alerts.append({
            "component": a.get("component", "Unknown"),
            "alert_type": _alert_type(a.get("component", "")),
            "severity": a.get("severity", "medium"),
            "message": a.get("message", ""),
            "estimated_cost": None,
            "due_in_km": None,
            "due_in_days": None,
            "source_id": None,
        })

    return HealthScoreResponse(
        score=result.get("score", 0),
        label=result.get("label", "unknown"),
        breakdown=score_breakdown,
        confidence=result.get("confidence", 0.5),
        alerts=alerts,
        signals=result.get("signals", []),
        model=result.get("model", "rule-based-fallback"),
    )


def _alert_type(component: str) -> str:
    """Map component to alert_type enum."""
    mapping = {
        "Scheduled": "service_overdue",
        "Oil": "service_overdue",
        "Major": "service_overdue",
        "Tire": "service_overdue",
        "Brake": "service_overdue",
        "Transmission": "service_overdue",
        "Coolant": "service_overdue",
        "OBD System": "obd_active",
        "Parts Inventory": "part_reorder",
        "Diagnostics": "diagnostic_open",
    }
    return mapping.get(component, "service_overdue")