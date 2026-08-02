"""MinIO (S3-compatible) storage helpers."""

import asyncio
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


def _ensure_bucket_sync() -> None:
    client = get_minio()
    if not client.bucket_exists(settings.MINIO_BUCKET):
        client.make_bucket(settings.MINIO_BUCKET)
        logger.info("created_minio_bucket", bucket=settings.MINIO_BUCKET)


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
