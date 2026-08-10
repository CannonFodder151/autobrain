"""Shared test environment.

Config fields that used to default to insecure credentials are now required
(fail closed). Provide non-secret placeholders here so the suite runs without a
real .env; individual test modules may override DATABASE_URL/SECRET_KEY.
"""

import os

os.environ.setdefault("POSTGRES_USER", "test-postgres-user")
os.environ.setdefault("POSTGRES_PASSWORD", "test-postgres-password")
os.environ.setdefault("POSTGRES_DB", "test-postgres-db")
os.environ.setdefault("MINIO_ACCESS_KEY", "test-minio-access-key")
os.environ.setdefault("MINIO_SECRET_KEY", "test-minio-secret-key")
os.environ.setdefault("MINIO_BUCKET", "test-minio-bucket")
