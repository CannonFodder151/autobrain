"""Owner-facing booking request API (AUT-3662).

Endpoints:
- POST /vehicles/{vehicle_id}/engineers/{engineer_id}/requests — submit booking request
- GET /engineers/requests — list owner's booking requests
- GET /engineers/requests/{request_id} — get booking request detail
- PATCH /engineers/requests/{request_id}/cancel — cancel booking request
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.engineer_dashboard import (
    BookingRequestCreate,
    BookingRequestOwnerDetail,
    BookingRequestOwnerSummary,
)
from app.services.engineer_dashboard import (
    cancel_booking_request,
    create_booking_request,
    get_booking_request_for_owner,
    get_owner_booking_requests,
    notify_engineer_booking_request,
)

# Nested router: POST to a specific engineer on a specific vehicle
submit_router = APIRouter(
    prefix="/vehicles/{vehicle_id}/engineers/{engineer_id}/requests",
    tags=["booking-requests"],
)

# Owner router: list/detail/cancel across all their vehicles
owner_router = APIRouter(prefix="/engineers/requests", tags=["booking-requests"])


@submit_router.post("", response_model=dict, status_code=201)
async def submit_booking_request(
    vehicle_id: str,
    engineer_id: str,
    payload: BookingRequestCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Submit a booking request to an engineer for a specific vehicle.

    Acceptance: Owner can submit request with vehicle details, modification info,
    symptoms, and preferred date/time. System generates pre-check report.
    Engineer receives notification of the new request.
    """
    result = await create_booking_request(
        db=db,
        user_id=user.id,
        vehicle_id=vehicle_id,
        engineer_id=engineer_id,
        payload=payload.model_dump(exclude_unset=True),
    )
    if not result:
        raise HTTPException(status_code=404, detail="Engineer not found or inactive, or vehicle not accessible")

    # Notify the engineer of the new booking request
    await notify_engineer_booking_request(db, engineer_id, payload)

    return result


@owner_router.get("", response_model=list[BookingRequestOwnerSummary])
async def list_owner_booking_requests(
    status: str | None = Query(None, description="Filter by status: pending/accepted/rejected/completed/cancelled"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """List all booking requests submitted by the current user (across all vehicles)."""
    results, _ = await get_owner_booking_requests(
        db, user.id, status=status, page=page, limit=limit
    )
    return results


@owner_router.get("/{request_id}", response_model=BookingRequestOwnerDetail)
async def get_booking_request_detail(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Get booking request detail for the owner."""
    detail = await get_booking_request_for_owner(db, user.id, request_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Booking request not found")
    return detail


@owner_router.patch("/{request_id}/cancel", response_model=dict)
async def cancel_request(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Cancel a pending booking request."""
    result = await cancel_booking_request(db, user.id, request_id)
    if not result:
        raise HTTPException(status_code=404, detail="Booking request not found or cannot be cancelled")
    return result