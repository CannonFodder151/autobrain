"""Media upload endpoints"""

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_premium, require_premium_write
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.user import User
from app.social.media import MAX_UPLOAD_BYTES, MediaError, read_upload, signed_url, upload_photo
from app.social.rate_limit import social_rate_limit, social_user_rate_limit

logger = get_logger(__name__)

router = APIRouter(dependencies=[Depends(require_premium)])


def _reject_oversized_content_length(request: Request) -> None:
    cl = request.headers.get("content-length")
    if cl and int(cl) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Upload too large (max {MAX_UPLOAD_BYTES // 1024 // 1024} MB)",
        )


@router.post("/uploads", status_code=201)
async def upload(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
):
    """Upload a photo for a build post."""
    _reject_oversized_content_length(request)

    data = await read_upload(file)
    try:
        photo = await upload_photo(db, user.id, data, file.content_type or "image/jpeg")
    except MediaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "id": photo.id,
        "key": photo.key,
        "url": photo.url,
        "thumb_url": photo.thumb_url,
        "expires_at": photo.expires_at.isoformat() if photo.expires_at else None,
    }
