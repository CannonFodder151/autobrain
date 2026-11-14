"""Shared test environment.

Config fields that used to default to insecure credentials are now required
(fail closed). Provide non-secret placeholders here so the suite runs without a
real .env; individual test modules may override DATABASE_URL/SECRET_KEY.

DATABASE_URL is forced to an asyncpg URL before any app module is imported so
the suite runs regardless of the surrounding shell environment (e.g. a host
that exports a psycopg2-style DATABASE_URL for other services).

Pin the shared app.db.session engine to Postgres early so later test modules
that override DATABASE_URL do not re-bind the engine to SQLite (AUT-296).
SQLite-backed test modules create their own engines and are unaffected.
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

# Force engine creation against the pinned Postgres URL so later test modules
# that set DATABASE_URL=sqlite cannot re-bind the shared engine. SQLite test
# modules (e.g. test_aut207, test_aut3447, test_device_verify_api) create their
# own engines and are unaffected by this pin.
from app.db.session import _pin_engine  # noqa: E402
_pin_engine()
