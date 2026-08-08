"""Global search endpoint — hybrid keyword + semantic search."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.services.search import semantic_search

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


@router.get("", response_model=list[SearchResult])
async def search(
    q: str = Query(..., min_length=1, max_length=500, alias="q"),
    entity_types: str | None = Query(None, description="Comma-separated entity types"),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Hybrid search across diagnostics, services, modifications, and receipts."""
    types = [t.strip() for t in entity_types.split(",")] if entity_types else None
    results = await semantic_search(
        db=db,
        query=q,
        vehicle_id=None,  # search all user's vehicles; add filter if needed
        entity_types=types,
        limit=limit,
    )
    return results
