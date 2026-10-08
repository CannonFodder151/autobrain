#!/usr/bin/env python3
"""Generate OpenAPI spec from FastAPI app.

Usage:
    python scripts/generate_openapi.py

Requires:
    - FastAPI app dependencies installed
    - Database connection (for full schema generation)
"""

import json
import os
import sys
from pathlib import Path

# Set required environment variables before importing app
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("POSTGRES_USER", "postgres")
os.environ.setdefault("POSTGRES_PASSWORD", "postgres")
os.environ.setdefault("MINIO_ACCESS_KEY", "minio")
os.environ.setdefault("MINIO_SECRET_KEY", "minio123")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/autobrain")
os.environ.setdefault("SECRET_KEY", "dev-secret-key-change-in-production")
os.environ.setdefault("AI_ROUTER_URL", "http://10.0.3.17:20128/v1")
os.environ.setdefault("AI_ROUTER_API_KEY", "dev-key")
os.environ.setdefault("AI_GATEWAY_API_KEY", "dev-gateway-key")
os.environ.setdefault("APP_VERSION", "0.3.4")
os.environ.setdefault("API_V1_PREFIX", "/api/v1")
os.environ.setdefault("CORS_ALLOWED_ORIGINS", '["http://localhost:3000"]')

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.main import app  # noqa: E402


def main():
    openapi_spec = app.openapi()
    output_path = Path(__file__).parent.parent / "openapi.json"
    with open(output_path, "w") as f:
        json.dump(openapi_spec, f, indent=2)
    print(f"OpenAPI spec generated at {output_path}")


if __name__ == "__main__":
    main()
