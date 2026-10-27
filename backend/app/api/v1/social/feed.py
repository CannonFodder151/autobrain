"""Feed endpoints: /feed, /my-posts"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_premium
from app.db.session import get_db
from app.models.user import User
from app.social.federation import FederationUnavailable
from app.social.models import SocialBuild, get_server_config
from app.social.snapshot import build_snapshot
from app.api.v1.social.helpers import _serialize

router = APIRouter(dependencies=[Depends(require_premium)])


@router.get("/feed")
async def feed(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium),
):
    """Paginated feed of published builds (local + federated)."""
    from app.social.federation import get_federated_feed

    local = list(
        (await db.execute(
            select(SocialBuild)
            .where(SocialBuild.status == "published")
            .order_by(SocialBuild.created_at.desc())
            .offset(offset)
            .limit(limit)
        )).scalars().all()
    )

    federated = []
    try:
        federated = await get_federated_feed(db, limit=limit, offset=offset)
    except FederationUnavailable:
        pass

    builds = local + federated
    builds.sort(key=lambda b: b.created_at if b.created_at else 0, reverse=True)
    builds = builds[:limit]

    items = [await _serialize(db, b, user) for b in builds]
    return {"items": items, "limit": limit, "offset": offset}


@router.get("/my-posts")
async def my_posts(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium),
):
    """Author's own posts (published + drafts).

    The original endpoint returned a dict with an ``items`` list and pagination
    metadata. Tests expect this shape.
    """
    # Only return published posts for the author (matching original behavior)
    builds = list(
        (await db.execute(
            select(SocialBuild)
            .where(SocialBuild.author_user_id == user.id)
            .where(SocialBuild.status == "published")
            .order_by(SocialBuild.created_at.desc())
            .offset(offset)
            .limit(limit)
        )).scalars().all()
    )
    items = [await _serialize(db, b, user) for b in builds]
    return {"items": items, "limit": limit, "offset": offset}
