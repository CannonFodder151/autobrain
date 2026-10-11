"""Community Garage social routes — split into focused submodules.

All public names are re-exported so existing imports continue to work.
"""

from app.api.v1.social.feed import router as feed_router  # noqa: F401
from app.api.v1.social.posts import router as posts_router  # noqa: F401
from app.api.v1.social.comments import router as comments_router  # noqa: F401
from app.api.v1.social.likes import router as likes_router  # noqa: F401
from app.api.v1.social.moderation import router as moderation_router  # noqa: F401
from app.api.v1.social.share import router as share_router  # noqa: F401
from app.api.v1.social.uploads import router as uploads_router  # noqa: F401

# Re-export schemas for tests that import from app.api.v1.social
from app.api.v1.social.posts import PostCreate, PostUpdate  # noqa: F401
from app.api.v1.social.comments import CommentIn  # noqa: F401
from app.api.v1.social.moderation import ReportIn, FlagIn  # noqa: F401

# Re-export helper functions used by other modules
from app.api.v1.social.posts import _serialize, _get_published  # noqa: F401
from app.api.v1.social.federation import _sync_federation, _apply_event  # noqa: F401

# Aggregate router for inclusion in main API
from fastapi import APIRouter

router = APIRouter(prefix="/social", tags=["social"])
router.include_router(feed_router)
router.include_router(posts_router)
router.include_router(comments_router)
router.include_router(likes_router)
router.include_router(moderation_router)
router.include_router(share_router)
router.include_router(uploads_router)

__all__ = [
    "router",
    "PostCreate",
    "PostUpdate",
    "CommentIn",
    "ReportIn",
    "FlagIn",
    "_serialize",
    "_get_published",
    "_sync_federation",
    "_apply_event",
]