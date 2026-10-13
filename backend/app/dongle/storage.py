"""MinIO blob storage + signed URLs. Pluggable (minio | fake) for tests."""

from __future__ import annotations

import abc
from datetime import timedelta

from minio import Minio

from .config import settings

class Storage(abc.ABC):
    @abc.abstractmethod
    async def presigned_url(self, key: str, ttl: timedelta) -> str: ...

    @abc.abstractmethod
    async def upload(self, key: str, data: bytes, content_type: str) -> str: ...

    @abc.abstractmethod
    async def get(self, key: str) -> bytes: ...

    @abc.abstractmethod
    async def remove(self, key: str) -> None: ...

class MinioStorage(Storage):
    def __init__(self) -> None:
        ak, sk = settings.minio_creds()
        self._client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=ak,
            secret_key=sk,
            secure=settings.MINIO_SECURE,
        )
        self._bucket = settings.MINIO_BUCKET

    async def presigned_url(self, key: str, ttl: timedelta) -> str:
        import asyncio

        def _presign():
            return self._client.presigned_get_object(
                self._bucket, key, expires=ttl
            )

        url = await asyncio.to_thread(_presign)
        return _externalize_url(url)

    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        import asyncio
        from io import BytesIO

        def _up():
            self._client.put_object(
                self._bucket, key, BytesIO(data), length=len(data),
                content_type=content_type,
            )

        await asyncio.to_thread(_up)
        url = await self.presigned_url(key, timedelta(seconds=settings.SIGNED_URL_TTL_SECONDS))
        return url

    async def get(self, key: str) -> bytes:
        import asyncio

        def _get():
            resp = self._client.get_object(self._bucket, key)
            try:
                return resp.read()
            finally:
                resp.close()
                resp.release_conn()

        return await asyncio.to_thread(_get)

    async def remove(self, key: str) -> None:
        import asyncio

        await asyncio.to_thread(self._client.remove_object, self._bucket, key)

def _externalize_url(url: str) -> str:
    """Map the internal MinIO host to the external public endpoint.

    The MinIO SDK returns presigned URLs using the internal container DNS name
    (e.g. http://minio:9000/bucket/key?signature). External clients need the
    public hostname. If MINIO_EXTERNAL_ENDPOINT is unset, return the URL
    unchanged (internal-only consumers).
    """
    if not settings.MINIO_EXTERNAL_ENDPOINT:
        return url
    scheme = "https" if settings.MINIO_SECURE else "http"
    internal = f"{scheme}://{settings.MINIO_ENDPOINT}"
    if url.startswith(internal):
        return f"{scheme}://{settings.MINIO_EXTERNAL_ENDPOINT}{url[len(internal):]}"
    return url

class FakeStorage(Storage):
    """In-memory storage for tests / local smoke runs without MinIO."""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    async def presigned_url(self, key: str, ttl: timedelta) -> str:
        return f"https://dongle-fake/{key}?expires={int(ttl.total_seconds())}"

    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        self._objects[key] = data
        return await self.presigned_url(key, timedelta(seconds=settings.SIGNED_URL_TTL_SECONDS))

    async def get(self, key: str) -> bytes:
        return self._objects.get(key, b"")

    async def remove(self, key: str) -> None:
        self._objects.pop(key, None)

def get_storage() -> Storage:
    if settings.ENVIRONMENT == "test" or not settings.minio_creds()[0]:
        return FakeStorage()
    return MinioStorage()