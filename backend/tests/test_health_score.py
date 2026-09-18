"""Unit tests for Vehicle Health Score (AUT-3359)."""

import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./t.db")
os.environ.setdefault("SECRET_KEY", "test-secret")

import uuid  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.db.session import SessionLocal, init_db  # noqa: E402
from app.models.diagnostic import Diagnostic  # noqa: E402
from app.models.fuel import FuelLog  # noqa: E402
from app.models.obd import ObdCode  # noqa: E402
from app.models.part import Part  # noqa: E402
from app.models.service import ServiceRecord  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.vehicle import Vehicle  # noqa: E402
from app.services.health_score import (  # noqa: E402
    _condition_score,
    _obd_penalty,
    compute_health_score,
)


def test_condition_score_excellent() -> None:
    assert _condition_score("excellent") == 20


def test_condition_score_good() -> None:
    assert _condition_score("good") == 15


def test_condition_score_fair() -> None:
    assert _condition_score("fair") == 10


def test_condition_score_poor() -> None:
    assert _condition_score("poor") == 0


def test_condition_score_unknown() -> None:
    assert _condition_score("unknown") == 0


def test_obd_penalty_empty() -> None:
    assert _obd_penalty([]) == 0


def test_obd_penalty_single_code() -> None:
    assert _obd_penalty(["P0301"]) == -30


def test_obd_penalty_multiple_codes() -> None:
    assert _obd_penalty(["P0301", "P0420"]) == -60


def _make_user(db: AsyncSession, email: str) -> User:
    user = User(
        id=str(uuid.uuid4()),
        email=email,
        display_name="T",
        hashed_password="x",
        max_vehicles=5,
    )
    db.add(user)
    return user


def _make_vehicle(db: AsyncSession, user: User) -> Vehicle:
    v = Vehicle(
        id=str(uuid.uuid4()),
        user_id=user.id,
        nickname="Test Car",
        condition="good",
    )
    db.add(v)
    return v


@pytest.mark.asyncio
async def test_health_score_empty_vehicle() -> None:
    """A vehicle with no data should return a low score (condition only)."""
    await init_db()
    async with SessionLocal() as db:
        user = _make_user(db, f"hs-{uuid.uuid4().hex[:8]}@x.com")
        vehicle = _make_vehicle(db, user)
        await db.commit()
        result = await compute_health_score(db, vehicle.id)
        assert result["score"] > 0  # at least condition contributes
        assert result["score"] <= 20  # condition="good" => 15, fuel=0, others neutral
        assert result["grade"] in ("F", "D")
        assert "No fuel efficiency data" in result["alerts"]


@pytest.mark.asyncio
async def test_health_score_with_obd_codes() -> None:
    """Active OBD codes should penalise the score significantly."""
    await init_db()
    async with SessionLocal() as db:
        user = _make_user(db, f"hs-obd-{uuid.uuid4().hex[:8]}@x.com")
        vehicle = _make_vehicle(db, user)
        db.add(ObdCode(vehicle_id=vehicle.id, code="P0301"))
        await db.commit()
        result = await compute_health_score(db, vehicle.id)
        # good=15 + obd=-30 = -15 => clamped to 0
        assert result["score"] == 0
        assert result["grade"] == "F"
        assert any("OBD" in a or "fault" in a.lower() for a in result["alerts"])


@pytest.mark.asyncio
async def test_health_score_with_active_diagnostic() -> None:
    """An active high-severity diagnostic should penalise the score."""
    await init_db()
    async with SessionLocal() as db:
        user = _make_user(db, f"hs-diag-{uuid.uuid4().hex[:8]}@x.com")
        vehicle = _make_vehicle(db, user)
        db.add(
            Diagnostic(
                vehicle_id=vehicle.id,
                symptoms="Engine knocking",
                ai_response='{"severity": "high"}',
                severity="high",
                status="open",
            )
        )
        await db.commit()
        result = await compute_health_score(db, vehicle.id)
        # good=15 + diag=-20 = -5 => clamped to 0
        assert result["score"] == 0
        assert result["grade"] == "F"
        assert any("severity" in a.lower() or "diagnostic" in a.lower() for a in result["alerts"])


@pytest.mark.asyncio
async def test_health_score_with_fuel_efficiency() -> None:
    """Good fuel efficiency should contribute positively."""
    await init_db()
    async with SessionLocal() as db:
        user = _make_user(db, f"hs-fuel-{uuid.uuid4().hex[:8]}@x.com")
        vehicle = _make_vehicle(db, user)
        # Add fuel logs that give good efficiency
        # 40L over 800km = 5 L/100km
        db.add(
            FuelLog(
                vehicle_id=vehicle.id,
                fill_date=__import__("datetime").date(2026, 1, 1),
                odometer_km=10000,
                litres=40.0,
                price_per_litre=1.6,
                total_cost=64.0,
                l_per_100km=5.0,
            )
        )
        await db.commit()
        result = await compute_health_score(db, vehicle.id)
        # good=15 + fuel=15 = 30
        assert result["score"] == 30
        assert result["grade"] == "F"
        assert "l/100km" in result["breakdown"]["fuel_efficiency"]["detail"]


@pytest.mark.asyncio
async def test_health_score_100_possible() -> None:
    """A vehicle with perfect condition and good fuel data should score high."""
    await init_db()
    async with SessionLocal() as db:
        user = _make_user(db, f"hs-perf-{uuid.uuid4().hex[:8]}@x.com")
        vehicle = _make_vehicle(db, user)
        vehicle.condition = "excellent"
        db.add(
            FuelLog(
                vehicle_id=vehicle.id,
                fill_date=__import__("datetime").date(2026, 1, 1),
                odometer_km=10000,
                litres=30.0,
                price_per_litre=1.6,
                total_cost=48.0,
                l_per_100km=4.0,
            )
        )
        await db.commit()
        result = await compute_health_score(db, vehicle.id)
        # excellent=20 + fuel=15 = 35
        assert result["score"] == 35
        assert result["grade"] in ("F", "D")
        assert result["score"] > 0
        # No alerts for OBD/diags since none exist
        assert not any("OBD" in a for a in result["alerts"])


@pytest.mark.asyncio
async def test_health_score_resolved_diagnostic_not_penalised() -> None:
    """Resolved diagnostics should not penalise the score."""
    await init_db()
    async with SessionLocal() as db:
        user = _make_user(db, f"hs-res-{uuid.uuid4().hex[:8]}@x.com")
        vehicle = _make_vehicle(db, user)
        db.add(
            Diagnostic(
                vehicle_id=vehicle.id,
                symptoms="Engine knock",
                ai_response='{"severity": "critical"}',
                severity="critical",
                status="resolved",
            )
        )
        await db.commit()
        result = await compute_health_score(db, vehicle.id)
        # good=15 + no diag penalty (resolved) = 15
        assert result["score"] == 15
        assert result["grade"] == "F"
        # No diagnostic severity alert
        assert not any("severity" in a.lower() for a in result["alerts"])


@pytest.mark.asyncio
async def test_health_score_resolved_obd_not_penalised() -> None:
    """Resolved OBD codes should not penalise the score."""
    await init_db()
    async with SessionLocal() as db:
        user = _make_user(db, f"hs-resobd-{uuid.uuid4().hex[:8]}@x.com")
        vehicle = _make_vehicle(db, user)
        db.add(ObdCode(vehicle_id=vehicle.id, code="P0301", is_resolved=True))
        await db.commit()
        result = await compute_health_score(db, vehicle.id)
        # good=15 + no OBD penalty (resolved) = 15
        assert result["score"] == 15
        assert not any("OBD" in a or "fault" in a.lower() for a in result["alerts"])