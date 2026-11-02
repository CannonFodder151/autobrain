from fastapi import APIRouter

from app.api.v1.social.posts import router as posts_router
from app.api.v1.social.comments import router as comments_router
from app.api.v1.social.reactions import router as reactions_router
from app.api.v1.social.feed import router as feed_router

router = APIRouter(prefix="/social")
router.include_router(posts_router)
router.include_router(comments_router)
router.include_router(reactions_router)
router.include_router(feed_router)

from app.api.v1.social.common import require_social_feature
from app.api.v1.social.common import _tombstone_removed_build, _sync_federation
