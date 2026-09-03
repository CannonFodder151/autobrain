"""Social media handling: webp-compress on upload, MinIO storage, signed URLs.

No AI in this path — purely deterministic image processing (Pillow).
"""

import asyncio
import uuid
from io import BytesIO

from pillow_heif import register_heif_opener
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.storage import ensure_bucket, presigned_url, upload_object

# iPhone default camera format — Pillow cannot decode it until the HEIF opener
# is registered (deterministic, no AI). pillow-heif bundles libheif, so the
# slim base image needs no extra apt packages.
register_heif_opener()

# Input gate matches the 15MB caps used by receipts/fuel/logbook photo
# uploads. The stored object is still downscaled to 2048px + webp here, so a
# bigger input costs no extra storage/bandwidth on disk.
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
UPLOAD_READ_CHUNK = 64 * 1024
MAX_IMAGE_DIMENSION = 2048
# Raster formats Pillow can decode; everything lands in MinIO as webp.
# image/heic + image/heif are iPhone/Android camera defaults (AUT-764).
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
WEBP_QUALITY = 82


class MediaError(ValueError):
    pass


def compress_to_webp(data: bytes, content_type: str | None = None) -> bytes:
    """Decode a raster image and re-encode as webp (deterministic, lossy).

    Raises MediaError for anything Pillow cannot decode (including
    DecompressionBombError). Images larger than 2048px on their longest side
    are downscaled to fit. RGBA is preserved (webp supports alpha); other
    modes are flattened to RGB.
    """
    try:
        img = Image.open(BytesIO(data))
        img.load()
    except Image.DecompressionBombError as exc:
        raise MediaError("Image exceeds the maximum allowed pixel dimensions") from exc
    except (UnidentifiedImageError, OSError) as exc:
        raise MediaError(
            "That photo can't be processed. Use JPEG, PNG, WebP or HEIC."
        ) from exc
    # Bake EXIF orientation into pixels (AUT-1946). Phone cameras (esp. iPhone)
    # mark portrait shots with Orientation=6/8 and leave the raw pixels rotated
    # the other way; the encoded webp would otherwise display sideways. Doing
    # this server-side is deterministic — every viewer sees the same orientation.
    img = ImageOps.exif_transpose(img) or img
    if max(img.size) > MAX_IMAGE_DIMENSION:
        img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.LANCZOS)
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


async def read_upload(file) -> bytes:
    """Stream a multipart upload into memory, aborting once past the cap.

    Guards against clients that lie about or omit Content-Length: the whole
    body is never buffered. Raises MediaError when MAX_UPLOAD_BYTES is exceeded.
    """
    chunks: list[bytes] = []
    buffered = 0
    while True:
        chunk = await file.read(UPLOAD_READ_CHUNK)
        if not chunk:
            return b"".join(chunks)
        buffered += len(chunk)
        if buffered > MAX_UPLOAD_BYTES:
            raise MediaError("File too large (max 15MB)")
        chunks.append(chunk)


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
