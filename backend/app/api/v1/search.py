"""Global search endpoint — hybrid keyword + semantic search."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.services.ownership import get_accessible_vehicle
from app.models.share import VehicleShare
from app.models.user import User
from app.models.vehicle import Vehicle
from app.services.search import ENTITY_TYPES, semantic_search

router = APIRouter(prefix="/search", tags=["search"])


class SearchRequest(BaseModel):
    q: str = Field(..., min_length=1, max_length=500, description="Search query")
    entity_types: list[str] | None = Field(
        default=None,
        description="Limit to these entity types (diagnostic/service/modification/receipt)",
    )
    limit: int = Field(default=20, ge=1, le=100)


class SearchResult(BaseModel):
    id: str
    type: str
    score: float
    method: str  # "keyword" or "vector"
    vehicle_id: str | None = None
    created_at: str | None = None
    # Entity-specific fields:
    symptoms: str | None = None
    summary: str | None = None
    severity: str | None = None
    description: str | None = None
    service_type: str | None = None
    workshop: str | None = None
    cost: float | None = None
    name: str | None = None
    category: str | None = None
    brand: str | None = None
    vendor: str | None = None
    original_name: str | None = None
    total: float | None = None


async def _accessible_vehicle_ids(db: AsyncSession, user: User) -> list[str]:
    """Vehicle IDs the user owns or has an accepted share on."""
    owned = (await db.scalars(
        select(Vehicle.id).where(Vehicle.user_id == user.id)
    )).all()
    shared = (await db.scalars(
        select(VehicleShare.vehicle_id).where(
            VehicleShare.invitee_user_id == user.id,
            VehicleShare.status == "accepted",
        )
    )).all()
    return list(set(owned) | set(shared))


@router.get("", response_model=list[SearchResult])
async def search(
    q: str = Query(..., min_length=1, max_length=500, alias="q"),
    entity_types: str | None = Query(None, description="Comma-separated entity types"),
    limit: int = Query(20, ge=1, le=100),
    vehicle_id: str | None = Query(None, description="Restrict search to this vehicle"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Hybrid search across diagnostics, services, modifications, and receipts.

    Results are scoped to the requesting user's own vehicles plus vehicles
    shared with them (accepted shares only).
    """
    types = [t.strip() for t in entity_types.split(",") if t.strip()] if entity_types else None
    if types:
        unknown = [t for t in types if t not in ENTITY_TYPES]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown entity types: {', '.join(unknown)}",
            )

    if vehicle_id:
        await get_accessible_vehicle(db, vehicle_id, user)
        vehicle_ids = [vehicle_id]
    else:
        vehicle_ids = await _accessible_vehicle_ids(db, user)

    results = await semantic_search(
        db=db,
        query=q,
        vehicle_ids=vehicle_ids,
        entity_types=types,
        limit=limit,
    )
    return results
