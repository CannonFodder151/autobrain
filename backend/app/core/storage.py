"""MinIO (S3-compatible) storage helpers."""

import asyncio
import json
from io import BytesIO
from typing import BinaryIO

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
    bucket = settings.MINIO_BUCKET
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
        logger.info("created_minio_bucket", bucket=bucket)
    # Public read policy — replaces the old minio-init container's
    # `mc anonymous set download` so upload URLs work without a one-shot container.
    policy = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{bucket}/*"],
                }
            ],
        }
    )
    client.set_bucket_policy(bucket, policy)


async def upload_object(key: str, data: bytes, content_type: str) -> str:
    def _upload() -> None:
        get_minio().put_object(
            settings.MINIO_BUCKET,
            key,
            BytesIO(data),
            length=len(data),
            content_type=content_type,
        )

    await asyncio.to_thread(_upload)
    scheme = "https" if settings.MINIO_SECURE else "http"
    host = settings.MINIO_PUBLIC_ENDPOINT.rstrip("/")
    return f"{host}/{settings.MINIO_BUCKET}/{key}"


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
