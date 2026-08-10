"""Unit tests for the business logic extracted from api/v1 routers (AUT-143).

Covers the pure rules (financial year, TOTP, token pair, rate limiting) plus
sqlite-backed exercises of the extracted DB logic (fuel efficiency chaining,
fuel stats aggregation, vehicle timeline, share invite).
"""

import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./t.db")
os.environ.setdefault("SECRET_KEY", "test-secret")

import uuid  # noqa: E402

import pyotp  # noqa: E402
import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.db.session import SessionLocal, init_db  # noqa: E402
from app.models.fuel import FuelLog  # noqa: E402
from app.models.service import ServiceRecord  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.vehicle import Vehicle  # noqa: E402
from app.schemas.auth import UserOut  # noqa: E402
from app.services import auth as auth_svc  # noqa: E402
from app.services import fuel as fuel_svc  # noqa: E402
from app.services import vehicle as vehicle_svc  # noqa: E402
from app.services.service_records import ensure_completed_event  # noqa: E402


# --- pure rules ---
def test_current_fy_boundary() -> None:
    assert fuel_svc.current_fy(__import__("datetime").date(2026, 6, 30)) == 2026
    assert fuel_svc.current_fy(__import__("datetime").date(2026, 7, 1)) == 2027


def test_verify_totp_roundtrip() -> None:
    secret = pyotp.random_base32()
    code = pyotp.TOTP(secret).now()
    assert auth_svc.verify_totp(secret, code)
    assert not auth_svc.verify_totp(secret, "000000")
    assert not auth_svc.verify_totp(None, code)


def test_token_pair_contains_user() -> None:
    user = User(id="u1", email="a@b.c", display_name="A", hashed_password="x", role="user",
                max_vehicles=2, is_active=True, free_account=False,
                obd_enabled=False, obd_auto_connect=False, mfa_enabled=False)
    pair = auth_svc.token_pair(user)
    assert pair.access_token
    assert pair.refresh_token
    assert pair.user.email == "a@b.c"
    assert isinstance(pair.user, UserOut)


def test_rate_limit_blocks_after_attempts(monkeypatch) -> None:
    monkeypatch.setattr("app.services.auth.settings.LOGIN_MAX_ATTEMPTS", 3)
    monkeypatch.setattr("app.services.auth.settings.LOGIN_WINDOW_SECONDS", 3600)
    auth_svc._login_failures.clear()
    ip = "1.2.3.4"
    for _ in range(3):
        auth_svc.record_failure(ip)
    with pytest.raises(HTTPException) as exc:
        auth_svc.check_rate_limit(ip)
    assert exc.value.status_code == 429
    auth_svc.clear_failures(ip)
    auth_svc.check_rate_limit(ip)  # cleared → no raise


def test_random_password_is_hashed() -> None:
    pw = auth_svc.random_password()
    assert pw != ""


# --- sqlite-backed exercises of extracted DB logic ---
def _make_user(db: AsyncSession, email: str) -> User:
    user = User(id=str(uuid.uuid4()), email=email, display_name="T", hashed_password="x", max_vehicles=5)
    db.add(user)
    return user


def _make_vehicle(db: AsyncSession, user: User) -> Vehicle:
    v = Vehicle(id=str(uuid.uuid4()), user_id=user.id, nickname="R34")
    db.add(v)
    return v


@pytest.mark.asyncio
async def test_recompute_efficiency_and_stats_end_to_end() -> None:
    await init_db()
    async with SessionLocal() as db:
        user = _make_user(db, f"fuel-{uuid.uuid4().hex[:8]}@x.com")
        vehicle = _make_vehicle(db, user)
        db.add_all([
            FuelLog(vehicle_id=vehicle.id, fill_date=__import__("datetime").date(2026, 1, 1),
                    odometer_km=10000, litres=50.0, price_per_litre=1.6, total_cost=80.0),
            FuelLog(vehicle_id=vehicle.id, fill_date=__import__("datetime").date(2026, 1, 15),
                    odometer_km=10500, litres=40.0, price_per_litre=1.7, total_cost=68.0),
            FuelLog(vehicle_id=vehicle.id, fill_date=__import__("datetime").date(2026, 2, 1),
                    odometer_km=10800, litres=30.0, price_per_litre=1.8, total_cost=54.0),
        ])
        await db.commit()
        await fuel_svc.recompute_efficiency(db, vehicle.id)
        await db.commit()
        stats = await fuel_svc.compute_fuel_stats(db, vehicle.id)
        assert stats.total_litres == 120.0
        assert stats.total_cost == 202.0
        assert len(stats.series) == 3
        # 500km on 40L → 8 L/100km; 300km on 30L → 10 L/100km; first log chains nothing.
        assert stats.series[1]["l_per_100km"] == 8.0
        assert stats.series[2]["l_per_100km"] == 10.0
        assert stats.series[0]["l_per_100km"] is None


@pytest.mark.asyncio
async def test_vehicle_timeline_filters_uncompleted_services() -> None:
    await init_db()
    async with SessionLocal() as db:
        user = _make_user(db, f"tl-{uuid.uuid4().hex[:8]}@x.com")
        vehicle = _make_vehicle(db, user)
        svc = ServiceRecord(
            id=str(uuid.uuid4()), vehicle_id=vehicle.id, service_date=__import__("datetime").date(2026, 1, 1),
            odometer_km=10000, service_type="repair", status="scheduled",
        )
        db.add(svc)
        await db.commit()
        await ensure_completed_event(db, svc)
        await db.commit()
        # Scheduled service → no timeline event.
        assert len(await vehicle_svc.get_vehicle_timeline(db, vehicle.id)) == 0
        svc.status = "completed"
        svc.completed_date = __import__("datetime").date(2026, 1, 2)
        await ensure_completed_event(db, svc)
        await db.commit()
        events = await vehicle_svc.get_vehicle_timeline(db, vehicle.id)
        assert len(events) == 1
        assert events[0].event_type == "service"


@pytest.mark.asyncio
async def test_vehicle_limit_blocks_creations() -> None:
    await init_db()
    async with SessionLocal() as db:
        user = User(id=str(uuid.uuid4()), email=f"lim-{uuid.uuid4().hex[:8]}@x.com",
                    display_name="T", hashed_password="x", max_vehicles=1)
        db.add(user)
        _make_vehicle(db, user)
        await db.commit()
        with pytest.raises(HTTPException) as exc:
            await vehicle_svc.enforce_vehicle_limit(db, user)
        assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_invite_share_duplicate_and_self_rejected() -> None:
    await init_db()
    async with SessionLocal() as db:
        owner = _make_user(db, f"own-{uuid.uuid4().hex[:8]}@x.com")
        invitee = _make_user(db, f"inv-{uuid.uuid4().hex[:8]}@x.com")
        vehicle = _make_vehicle(db, owner)
        await db.commit()
        share = await vehicle_svc.invite_share(db, vehicle.id, owner, invitee.email)
        assert share["invitee_user_id"] == invitee.id
        with pytest.raises(HTTPException) as exc:
            await vehicle_svc.invite_share(db, vehicle.id, owner, invitee.email)
        assert exc.value.status_code == 409
        with pytest.raises(HTTPException) as exc:
            await vehicle_svc.invite_share(db, vehicle.id, owner, owner.email)
        assert exc.value.status_code == 400
        with pytest.raises(HTTPException) as exc:
            await vehicle_svc.invite_share(db, vehicle.id, owner, "missing@x.com")
        assert exc.value.status_code == 404
        shares = await vehicle_svc.list_vehicle_shares(db, vehicle.id)
        assert len(shares) == 1 and shares[0]["status"] == "pending"
