"""PHEV dual-source tracking routes (AUT-734).

Three endpoints for PHEV (plug-in hybrid) vehicles that track both ICE fuel
and EV charging:
  * GET  /vehicles/{vehicle_id}/phev-dashboard  — combined metrics + AI insights
  * GET  /vehicles/{vehicle_id}/phev-timeline   — unified fuel + EV trip timeline
  * POST /vehicles/{vehicle_id}/phev-export     — CSV export for reports
"""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.user import User
from app.schemas.phev import (
    PhevDashboardOut,
    PhevExportRequest,
    PhevTimelineOut,
)
from app.services.ownership import get_accessible_vehicle
from app.services import phev as phev_svc
from app.services.rate_limit import require_ai_rate_limit_best_effort

router = APIRouter(prefix="/vehicles/{vehicle_id}/phev", tags=["phev"])

logger = get_logger(__name__)


@router.get("/dashboard", response_model=PhevDashboardOut)
async def phev_dashboard(
    vehicle_id: str,
    period_days: int = Query(default=365, ge=1, le=3650),
    electricity_price_per_kwh: float | None = Query(
        default=None, ge=0, description="AUD/kWh override; defaults to 0.30"
    ),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    _: User = Depends(require_ai_rate_limit_best_effort),
) -> PhevDashboardOut:
    """Combined ICE + EV dashboard: distance, energy, efficiency, cost, AI insights."""
    await get_accessible_vehicle(db, vehicle_id, user)
    return await phev_svc.compute_phev_dashboard(
        db,
        vehicle_id,
        period_days=period_days,
        electricity_price_per_kwh=electricity_price_per_kwh,
    )


@router.get("/timeline", response_model=PhevTimelineOut)
async def phev_timeline(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PhevTimelineOut:
    """Unified PHEV usage timeline (fuel fill-ups + completed EV/ICE trips)."""
    await get_accessible_vehicle(db, vehicle_id, user)
    return await phev_svc.compute_phev_timeline(db, vehicle_id)


@router.post("/export")
async def phev_export(
    vehicle_id: str,
    payload: PhevExportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """CSV export of the dual-source PHEV dataset for reports.

    Defaults to the current Australian financial year when ``fy`` is omitted.
    """
    vehicle = await get_accessible_vehicle(db, vehicle_id, user)
    meta, csv_bytes = await phev_svc.build_phev_export(
        db,
        vehicle_id,
        vehicle.nickname,
        fy=payload.fy,
    )
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{meta.filename}"'},
    )
