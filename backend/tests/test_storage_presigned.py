"""Self-check for MinIO object URLs — private bucket (AUT-321).

Run:  cd backend && python3 -m pytest tests/test_storage_presigned.py -q
No external services: upload_object is exercised against a fake client and
the host-swap helper is tested directly.
"""

import asyncio
import os

os.environ.setdefault("POSTGRES_USER", "autobrain")
os.environ.setdefault("POSTGRES_PASSWORD", "autobrain")
os.environ.setdefault("MINIO_SECRET_KEY", "autobrain")
os.environ.setdefault("SECRET_KEY", "test-secret")

import app.core.storage as storage  # noqa: E402
from app.core.config import settings  # noqa: E402


def test_externalize_url_swaps_internal_host():
    settings.MINIO_ENDPOINT = "minio:9000"
    settings.MINIO_PUBLIC_ENDPOINT = "https://hosted.autobrainservice.app"
    url = "http://minio:9000/autobrain-assets/receipts/x.pdf?X-Amz-Signature=abc"
    assert storage._externalize_url(url) == (
        "https://hosted.autobrainservice.app/autobrain-assets/receipts/x.pdf?X-Amz-Signature=abc"
    )


def test_externalize_url_ignores_unrelated_host():
    assert storage._externalize_url("http://other:9000/foo") == "http://other:9000/foo"


def test_upload_object_returns_presigned_url():
    captured = {}

    class FakeClient:
        def put_object(self, bucket, key, data, length, content_type):
            captured["put"] = (bucket, key, length, content_type)

        def presigned_get_object(self, bucket, key, expires):
            return (
                f"http://minio:9000/{bucket}/{key}"
                f"?X-Amz-Signature=sig&X-Amz-Expires={int(expires.total_seconds())}"
            )

    settings.MINIO_ENDPOINT = "minio:9000"
    settings.MINIO_PUBLIC_ENDPOINT = "https://hosted.autobrainservice.app"
    storage._client = FakeClient()
    try:
        url = asyncio.run(storage.upload_object("receipts/v/x.pdf", b"%PDF-1.4", "application/pdf"))
    finally:
        storage._client = None

    assert captured["put"] == (settings.MINIO_BUCKET, "receipts/v/x.pdf", 8, "application/pdf")
    assert url.startswith(f"https://hosted.autobrainservice.app/{settings.MINIO_BUCKET}/receipts/v/x.pdf?")
    assert "X-Amz-Expires=3600" in url
    assert "Signature" in url
    print("ok: upload_object returns a time-limited presigned GET URL, bucket stays private")
