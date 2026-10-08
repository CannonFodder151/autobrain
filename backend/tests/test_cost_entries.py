"""Tests for cost tracking and analytics dashboard."""

import os

os.environ["DATABASE_URL"] = "postgresql+asyncpg://autobrain:autobrain@localhost:5432/autobrain"
os.environ["SECRET_KEY"] = "test-secret"
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("POSTGRES_USER", "test-postgres-user")
os.environ.setdefault("POSTGRES_PASSWORD", "test-postgres-password")
os.environ.setdefault("POSTGRES_DB", "test-postgres-db")
os.environ.setdefault("MINIO_ACCESS_KEY", "test-minio-access-key")
os.environ.setdefault("MINIO_SECRET_KEY", "test-minio-secret-key")
os.environ.setdefault("MINIO_BUCKET", "test-minio-bucket")

from datetime import date  # noqa: E402

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.deps import get_current_user  # noqa: E402
from app.api.v1.cost_entries import router  # noqa: E402
from app.models.cost_entry import CostCategory, CostEntry  # noqa: E402
from app.schemas.cost_entry import CostEntryCreate, CostDashboard, CategoryBreakdown  # noqa: E402


def _user():
    import types
    return types.SimpleNamespace(id="u1", free_account=False, role="user", is_active=True)


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def test_cost_category_values():
    """Verify all 6 required cost categories exist."""
    assert CostCategory.TRACK_DAY.value == "track_day"
    assert CostCategory.FUEL.value == "fuel"
    assert CostCategory.TIRES.value == "tires"
    assert CostCategory.PARTS.value == "parts"
    assert CostCategory.TRAVEL.value == "travel"
    assert CostCategory.INSURANCE.value == "insurance"


def test_cost_entry_schema_validation():
    """Verify CostEntryCreate validates required fields."""
    entry = CostEntryCreate(
        category=CostCategory.TRACK_DAY,
        amount=250.0,
        date=date(2026, 1, 15),
        track_name="Phillip Island",
        laps_completed=12,
    )
    assert entry.amount == 250.0
    assert entry.category == CostCategory.TRACK_DAY
    assert entry.track_name == "Phillip Island"
    assert entry.laps_completed == 12


def test_cost_entry_schema_optional_fields():
    """Verify optional fields default to None."""
    entry = CostEntryCreate(
        category=CostCategory.FUEL,
        amount=85.0,
        date=date(2026, 3, 20),
    )
    assert entry.odometer_km is None
    assert entry.description is None
    assert entry.vendor is None
    assert entry.receipt_id is None
    assert entry.track_name is None
    assert entry.laps_completed is None


def test_cost_dashboard_schema():
    """Verify CostDashboard schema accepts required fields."""
    dashboard = CostDashboard(
        total_spent=1500.0,
        category_breakdown=[
            {"category": CostCategory.TRACK_DAY, "total": 500.0, "count": 2},
            {"category": CostCategory.FUEL, "total": 300.0, "count": 4},
        ],
        cost_per_track_day=250.0,
        cost_per_lap=20.83,
        track_days_count=2,
        total_laps=24,
        monthly_trend=[{"month": "2026-01", "total": 500.0}],
    )
    assert dashboard.total_spent == 1500.0
    assert dashboard.cost_per_track_day == 250.0
    assert dashboard.cost_per_lap == 20.83


def test_unauthorized_access():
    """Verify cost entry routes require auth."""
    app = _app()
    with TestClient(app) as client:
        resp = client.get("/vehicles/test/cost-entries")
    assert resp.status_code in [401, 422]