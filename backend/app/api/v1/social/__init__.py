"""Community Garage social routes (AUT-294 rev 7, AUT-332).

Feature gate: every route 403s with "Disabled by your admin" when the feature
toggle is off, and requires premium entitlement (rev 4). Federation off = the
feed still works, local builds only.

Subpackage layout:
- posts.py: Post CRUD, sharing, uploads, flags
- comments.py: Comment routes
- reactions.py: Like routes
- feed.py: Feed and my-posts routes
- _common.py: Shared helpers (serialization, federation sync)

Backwards-compatibility re-exports so `app.api.v1` can keep importing
`social.router` / `social.require_social_feature` / `social._sync_federation`
/ `social._tombstone_removed_build` / `social._get_published` unchanged.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.social.models import get_server_config

from app.api.v1.social._common import (
    _apply_event,
    _comment_count,
    _get_published,
    _like_count,
    _plaintext,
    _purge_build,
    _push_event_safe,
    _push_outbox_safe,
    _serialize,
    _sync_federation,
    _tombstone_removed_build,
)
from app.social.media import read_upload
from app.api.v1.social.comments import router as comments_router
from app.api.v1.social.feed import router as feed_router
from app.api.v1.social.posts import router as posts_router
from app.api.v1.social.reactions import router as reactions_router

async def require_social_feature(db: AsyncSession = Depends(get_db)) -> None:
    cfg = await get_server_config(db)
    if not cfg.feature_enabled:
        raise HTTPException(status_code=403, detail="Disabled by your admin")


router = APIRouter(
    prefix="/social",
    tags=["social"],
    dependencies=[Depends(require_social_feature)],
)

router.include_router(feed_router)
router.include_router(posts_router)
router.include_router(comments_router)
router.include_router(reactions_router)


# Re-export Pydantic models for backward compatibility
from app.api.v1.social._common import (
    CommentIn,
    FlagIn,
    PostCreate,
    PostUpdate,
    ReportIn,
    ShareScopeIn,
)

__all__ = [
    "router",
    "require_social_feature",
    "_sync_federation",
    "_tombstone_removed_build",
    "_get_published",
    "_apply_event",
    "_comment_count",
    "_like_count",
    "_plaintext",
    "_purge_build",
    "_push_event_safe",
    "_push_outbox_safe",
    "_serialize",
    "ShareScopeIn",
    "PostCreate",
    "CommentIn",
    "ReportIn",
    "PostUpdate",
    "FlagIn",
    "read_upload",
]