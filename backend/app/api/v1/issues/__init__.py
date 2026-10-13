"""Community Garage Issues Blog — split into focused submodules.

All public names are re-exported so existing imports continue to work.
"""

from app.api.v1.issues.posts import router as posts_router  # noqa: F401
from app.api.v1.issues.comments import router as comments_router  # noqa: F401
from app.api.v1.issues.moderation import router as moderation_router  # noqa: F401
from app.api.v1.issues.federation import (
    pull_remote_issue,
    apply_issue_event,
)  # noqa: F401
from app.api.v1.issues.schemas import (
    IssueCreate,
    IssueUpdate,
    CommentIn,
    FlagIn,
    _plaintext,
    _vehicle_snapshot,
)  # noqa: F401

# Aggregate router for inclusion in main API
from fastapi import APIRouter
from app.api.v1.social import require_social_feature

router = APIRouter(
    prefix="/social/issues",
    tags=["social-issues"],
    dependencies=[Depends(require_social_feature)],
)
router.include_router(posts_router)
router.include_router(comments_router)
router.include_router(moderation_router)

__all__ = [
    "router",
    "IssueCreate",
    "IssueUpdate",
    "CommentIn",
    "FlagIn",
    "_plaintext",
    "_vehicle_snapshot",
    "pull_remote_issue",
    "apply_issue_event",
]