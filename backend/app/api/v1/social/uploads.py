"""Social upload endpoints."""

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_premium_write
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.user import User
from app.social.media import MAX_UPLOAD_BYTES, MediaError, read_upload, upload_photo
from app.social.models import SocialPhoto
from app.social.rate_limit import social_rate_limit

logger = get_logger(__name__)


router = APIRouter(prefix="/social", tags=["social"])


def _reject_oversized_content_length(request: Request) -> None:
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 15MB)")


@router.post("/uploads", status_code=201)
async def upload(
    _size_guard: None = Depends(_reject_oversized_content_length),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_premium_write),
    _rl: None = Depends(social_rate_limit(10)),
) -> dict:
    try:
        data = await read_upload(file)
        key, url, width, height = await upload_photo(user.id, data, file.content_type)
    except MediaError as exc:
        raise HTTPException(status_code=415, detail=str(exc))
    photo = SocialPhoto(uploader_user_id=user.id, file_key=key, width=width, height=height)
    db.add(photo)
    await db.commit()
    return {"id": photo.id, "url": url}