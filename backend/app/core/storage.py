"""MinIO (S3-compatible) storage helpers."""

import asyncio
from datetime import timedelta
from io import BytesIO

from minio import Minio

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_client: Minio | None = None


def get_minio() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
    return _client


async def ensure_bucket() -> None:
    await asyncio.to_thread(_ensure_bucket_sync)


_RECEIPT_MIME_BY_EXT = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "heic": "image/heic",
    "heif": "image/heic",
    "tiff": "image/tiff",
    "tif": "image/tiff",
}

_ALLOWED_IMAGE_TYPES = {
    "application/pdf", "image/jpeg", "image/png",
    "image/webp", "image/heic", "image/tiff",
}


def detect_mime(filename: str | None, content_type: str | None, data: bytes) -> str:
    """Best-effort MIME detection: magic bytes > filename extension > header.

    Clients (Flutter web/mobile) often send `application/octet-stream`, so the
    declared header alone is not trustworthy.
    """
    if data[:8] == b"%PDF-":
        return "application/pdf"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    ext = ""
    if filename and "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()
    if ext in _RECEIPT_MIME_BY_EXT:
        return _RECEIPT_MIME_BY_EXT[ext]
    if content_type in _ALLOWED_IMAGE_TYPES:
        return content_type
    if content_type and content_type.startswith("image/"):
        return content_type
    return content_type or "application/octet-stream"


def _ensure_bucket_sync() -> None:
    client = get_minio()
    if not client.bucket_exists(settings.MINIO_BUCKET):
        client.make_bucket(settings.MINIO_BUCKET)
        logger.info("created_minio_bucket", bucket=settings.MINIO_BUCKET)


async def upload_object(key: str, data: bytes, content_type: str) -> str:
    def _upload() -> str:
        client = get_minio()
        client.put_object(
            settings.MINIO_BUCKET,
            key,
            BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return client.presigned_get_object(settings.MINIO_BUCKET, key, expires=timedelta(minutes=15))

    url = await asyncio.to_thread(_upload)
    return _externalize_url(url)


def _externalize_url(url: str) -> str:
    """Swap the internal MinIO host for the externally reachable public endpoint.

    The presigned URL is signed against the host the client connected to
    (``MINIO_ENDPOINT``, e.g. ``minio:9000``), so the external proxy must
    preserve that Host header for the signature to validate — see the
    ``/autobrain-assets/`` location in ``docker/frontend/nginx.conf``.
    """
    scheme = "https" if settings.MINIO_SECURE else "http"
    internal = f"{scheme}://{settings.MINIO_ENDPOINT}"
    if url.startswith(internal):
        return settings.MINIO_PUBLIC_ENDPOINT.rstrip("/") + url[len(internal):]
    return url


async def presigned_url(key: str, expires: timedelta = timedelta(minutes=15)) -> str:
    """Short-lived presigned GET URL (externalized for the public endpoint)."""
    url = await asyncio.to_thread(
        get_minio().presigned_get_object, settings.MINIO_BUCKET, key, expires=expires
    )
    return _externalize_url(url)


async def get_object(key: str) -> bytes:
    def _get() -> bytes:
        resp = get_minio().get_object(settings.MINIO_BUCKET, key)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()

    return await asyncio.to_thread(_get)


async def delete_object(key: str) -> None:
    await asyncio.to_thread(get_minio().remove_object, settings.MINIO_BUCKET, key)
