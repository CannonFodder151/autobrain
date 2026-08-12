"""Social media handling: webp-compress on upload, MinIO storage, signed URLs.

No AI in this path — purely deterministic image processing (Pillow).
"""

import asyncio
import uuid
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from app.core.storage import ensure_bucket, presigned_url, upload_object

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
# Raster formats Pillow can decode; everything lands in MinIO as webp.
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
WEBP_QUALITY = 82


class MediaError(ValueError):
    pass


def compress_to_webp(data: bytes, content_type: str | None = None) -> bytes:
    """Decode a raster image and re-encode as webp (deterministic, lossy).

    Raises MediaError for anything Pillow cannot decode. RGBA is preserved
    (webp supports alpha); other modes are flattened to RGB.
    """
    try:
        img = Image.open(BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise MediaError("Uploaded file is not a decodable image") from exc
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "A" in img.mode else "RGB")
    out = BytesIO()
    img.save(out, format="WEBP", quality=WEBP_QUALITY, method=4)
    return out.getvalue()


def _webp_dimensions(data: bytes) -> tuple[int, int]:
    try:
        img = Image.open(BytesIO(data))
        return img.width, img.height
    except (UnidentifiedImageError, OSError):
        return 0, 0


def photo_key(user_id: str) -> str:
    return f"social/{user_id}/{uuid.uuid4().hex[:16]}.webp"


async def upload_photo(user_id: str, data: bytes, content_type: str | None = None) -> tuple[str, str, int, int]:
    """Compress to webp, store in MinIO, return (key, signed_url, width, height)."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise MediaError("File too large (max 15MB)")
    webp = await asyncio.to_thread(compress_to_webp, data, content_type)
    width, height = await asyncio.to_thread(_webp_dimensions, webp)
    key = photo_key(user_id)
    await ensure_bucket()
    url = await upload_object(key, webp, "image/webp")
    return key, url, width, height


async def signed_url(key: str) -> str:
    """Short-lived presigned GET URL for a stored object."""
    return await presigned_url(key)
