"""Smoke tests for core backend behaviour (auth + vehicles)."""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test-user:test-password@postgres:5432/autobrain")
os.environ.setdefault("SECRET_KEY", "test-secret")

import uuid  # noqa: E402

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from httpx import AsyncClient, ASGITransport  # noqa: E402

from app.api.deps import require_ai, require_write  # noqa: E402
from app.core.security import create_access_token, hash_password, verify_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.vehicle import Vehicle  # noqa: E402
from app.schemas.auth import AdminUserUpdate, UserCreate  # noqa: E402
from app.schemas.vehicle import VehicleCreate, VehicleOut, VehicleUpdate  # noqa: E402


def test_password_hashing() -> None:
    h = hash_password("hunter22")
    assert h != "hunter22"
    assert verify_password("hunter22", h)
    assert not verify_password("wrong", h)


def test_jwt_roundtrip() -> None:
    token = create_access_token("user-1")
    assert token


@pytest.mark.asyncio
async def test_health() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "autobrain-backend"
    assert "version" in data

@pytest.mark.asyncio
async def test_health_includes_version() -> None:
    """AUT-1962: Health endpoint must return version for CI gate validation."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data
    assert isinstance(data["version"], str)
    # Semver format check (major.minor.patch)
    parts = data["version"].split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)


@pytest.mark.asyncio
async def test_unauthorized_rejected() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/vehicles")
    assert resp.status_code == 401


def test_vehicle_limit_defaults() -> None:
    assert UserCreate(
        email="u@example.com", display_name="U", password="hunter22"
    ).max_vehicles == 1
    u = AdminUserUpdate(max_vehicles=5)
    assert u.max_vehicles == 5


def test_user_create_invite_allows_no_password() -> None:
    invite = UserCreate(email="invite@example.com", display_name="I", send_invite=True)
    assert invite.password is None
    assert invite.send_invite is True


def test_user_pending_defaults_and_admin_out() -> None:
    from app.schemas.auth import UserAdminOut

    assert "pending" in User.__table__.columns
    assert UserAdminOut(id="1", email="p@example.com", display_name="P", role="user",
                        is_active=True, mfa_enabled=False, pending=True).pending is True
    assert UserAdminOut(id="1", email="p@example.com", display_name="P", role="user",
                        is_active=True, mfa_enabled=False).pending is False


def test_vehicle_schema_accepts_limit() -> None:
    assert VehicleCreate(nickname="R34").is_primary is False


def test_vehicle_rego_state_field_wiring() -> None:
    """AUT-1903: rego state is a first-class, nullable vehicle attribute."""
    assert "rego_state" in Vehicle.__table__.columns
    assert "rego_state" in VehicleCreate.model_fields
    assert "rego_state" in VehicleUpdate.model_fields
    assert "rego_state" in VehicleOut.model_fields
    # Round-trips through create + update + output (nullable default None).
    assert VehicleCreate(nickname="C").rego_state is None
    assert VehicleCreate(nickname="C", rego_state="NSW").rego_state == "NSW"
    assert VehicleUpdate().rego_state is None
    assert VehicleUpdate(rego_state="VIC").rego_state == "VIC"


@pytest.mark.asyncio
async def test_demo_role_is_read_only() -> None:
    demo = User(id=str(uuid.uuid4()), email="demo@x", display_name="D",
                hashed_password="x", role="demo")
    with pytest.raises(HTTPException) as exc:
        await require_write(user=demo)
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        await require_ai(user=demo)
    assert exc.value.status_code == 403


def test_login_schema_handles_mfa_setup_flag() -> None:
    from app.schemas.auth import LoginResult

    r = LoginResult(mfa_setup_required=True, mfa_token="t")
    assert r.mfa_setup_required is True
    assert r.mfa_required is False
    assert r.mfa_token == "t"


def test_receipt_type_sniffing() -> None:
    from app.core.storage import detect_mime

    assert detect_mime("scan.pdf", "application/octet-stream", b"%PDF-1.4 ...") == "application/pdf"
    assert detect_mime("photo.jpg", "application/octet-stream", b"\xff\xd8\xff\xe0") == "image/jpeg"
    assert detect_mime("photo.png", "application/octet-stream", b"\x89PNG\r\n\x1a\n") == "image/png"
    assert detect_mime("scan.png", "image/png", b"\x00\x01\x02") == "image/png"
    assert detect_mime("scan.heic", "application/octet-stream", b"\x00\x00\x00\x18") == "image/heic"
    assert detect_mime("scan.bin", "application/octet-stream", b"\x00\x01\x02") == "application/octet-stream"


def test_pdf_export_builds() -> None:
    from app.services.export import export_service_history_pdf

    class R:
        service_date = "2026-01-01"
        odometer_km = 1000
        service_type = "scheduled"
        workshop = "Long Workshop Name That Wraps Across Multiple Lines In The PDF"
        cost = 120.5
        currency = "AUD"
        items = []
        notes = None

    pdf = export_service_history_pdf([R()], "Test Vehicle")
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 1000


def test_pdf_export_rego_in_title() -> None:
    from io import BytesIO
    from pypdf import PdfReader
    from app.services.export import export_service_history_pdf, export_build_sheet_pdf

    class R:
        service_date = "2026-01-01"
        odometer_km = 1000
        service_type = "scheduled"
        workshop = ""
        cost = 120.5
        currency = "AUD"
        items = []
        notes = None

    class M:
        install_date = "2026-06-01"
        name = "Cat-back exhaust"
        category = "Exhaust"
        brand = "XForce"
        cost = 500.0
        notes = None
        photo_keys = []

    pdf = export_service_history_pdf([R()], "Toyota Corolla", rego="3B4PV")
    assert pdf[:4] == b"%PDF"
    text = PdfReader(BytesIO(pdf)).pages[0].extract_text()
    assert "3B4PV" in text

    pdf_mod = export_build_sheet_pdf([M()], "Toyota Corolla", rego="3B4PV")
    assert pdf_mod[:4] == b"%PDF"
    text2 = PdfReader(BytesIO(pdf_mod)).pages[0].extract_text()
    assert "3B4PV" in text2

    # No rego - no double dash
    pdf_no_rego = export_service_history_pdf([R()], "Toyota Corolla")
    text3 = PdfReader(BytesIO(pdf_no_rego)).pages[0].extract_text()
    assert "---" not in text3


def test_notification_preference_defaults() -> None:
    from app.schemas.notification import NotificationPreferenceIn

    p = NotificationPreferenceIn(service_due_days=14, service_due_km=250)
    assert p.service_due_days == 14
    assert p.service_due_km == 250
    assert p.fuel_gap_km is None


def test_due_badge_formatting() -> None:
    from app.services.notify import _due_badge_html

    assert _due_badge_html("days", 3) == "3 days"
    assert _due_badge_html("days", 1) == "1 day"
    assert _due_badge_html("km", 500.0) == "500 km"
    assert _due_badge_html("km", None) == "now"
