"""Community Garage social routes subpackage.

Splits the former `app/api/v1/social.py` monolith into focused modules:
  - feed.py        — /feed, /my-posts endpoints
  - posts.py       — CRUD for posts (/posts, /posts/{id})
  - comments.py    — Comment routes (/posts/{id}/comments)
  - reactions.py   — Likes, flags, reports, share links
  - media.py       — Photo uploads (/uploads)
  - helpers.py     — Shared helpers (_serialize, _purge_build, etc.)

Backwards-compatibility re-exports so `app.api.v1` can keep importing
`social.router` unchanged.
"""

from app.api.v1.social.feed import router as feed_router
from app.api.v1.social.posts import router as posts_router
from app.api.v1.social.comments import router as comments_router
from app.api.v1.social.reactions import router as reactions_router
from app.api.v1.social.media import router as media_router
from app.api.v1.social.helpers import require_social_feature

from fastapi import APIRouter

router = APIRouter(prefix="/social", tags=["social"])

router.include_router(feed_router)
router.include_router(posts_router)
router.include_router(comments_router)
router.include_router(reactions_router)
router.include_router(media_router)

__all__ = ["router", "require_social_feature"]
