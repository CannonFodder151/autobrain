"""MinIO storage helpers."""

import structlog
from minio import Minio

from app.core.config import settings

logger = structlog.get_logger(__name__)


def get_minio_client() -> Minio:
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )


async def ensure_bucket() -> None:
    client = get_minio_client()
    if not client.bucket_exists(settings.MINIO_BUCKET):
        client.make_bucket(settings.MINIO_BUCKET)
        logger.info("bucket_created", bucket=settings.MINIO_BUCKET)
    else:
        logger.debug("bucket_exists", bucket=settings.MINIO_BUCKET)