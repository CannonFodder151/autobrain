"""Public version endpoints (no auth)."""

from fastapi import APIRouter

from app.core.config import settings
from app.services.version import check_mobile_latest_release

router = APIRouter(prefix="/version", tags=["version"])


@router.get("/mobile")
async def mobile_version() -> dict:
    """Latest published `autobrain-mobile` release from GitHub.

    The mobile app calls this on the server it is connected to, because the
    mobile repo is private and the app cannot reach GitHub directly. Returns
    the same shape as the admin version check; `latest_version` is the release
    tag without the leading `v`.
    """
    release = await check_mobile_latest_release()
    return {"repo": settings.MOBILE_GITHUB_REPO, **release}
