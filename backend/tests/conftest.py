"""Shared test environment.

Config fields that used to default to insecure credentials are now required
(fail closed). Provide non-secret placeholders here so the suite runs without a
real .env; individual test modules may override DATABASE_URL/SECRET_KEY.

DATABASE_URL is forced to an asyncpg URL before any app module is imported so
the suite runs regardless of the surrounding shell environment (e.g. a host
that exports a psycopg2-style DATABASE_URL for other services).
"""

import os

os.environ["DATABASE_URL"] = "postgresql+asyncpg://autobrain:autobrain@localhost:5432/autobrain"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["MARKET_DATA_URL"] = ""
os.environ["MARKET_DATA_API_KEY"] = ""

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("POSTGRES_USER", "test-postgres-user")
os.environ.setdefault("POSTGRES_PASSWORD", "test-postgres-password")
os.environ.setdefault("POSTGRES_DB", "test-postgres-db")
os.environ.setdefault("MINIO_ACCESS_KEY", "test-minio-access-key")
os.environ.setdefault("MINIO_SECRET_KEY", "test-minio-secret-key")
os.environ.setdefault("MINIO_BUCKET", "test-minio-bucket")
