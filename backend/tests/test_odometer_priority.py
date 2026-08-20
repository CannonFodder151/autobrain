"""AUT-1275: odometer source priority + no-rollback + auto service suggestion.

Priority: Dongle > Logbook > Fuel. No source may roll the odometer back —
entering a past fuel receipt or a past logbook trip after a newer reading must
not lower the vehicle odometer. When ``auto_suggest_service`` is on and the
odo passes an upcoming service's due threshold, a single ``service_due``
suggestion event is created (deduplicated).

Requires the compose Postgres (same as the rest of the suite).
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test-user:test-password@postgres:5432/autobrain")
os.environ.setdefault("SECRET_KEY", "test-secret")

import asyncio  # noqa: E402
import uuid  # noqa: E402

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.service import ServiceRecord  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.vehicle import Vehicle, VehicleEvent  # noqa: E402
from sqlalchemy import select  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _init_schema() -> None:
    asyncio.run(init_db())


async def _setup() -> dict:
    suffix = uuid.uuid4().hex[:8]
    async with SessionLocal() as db:
        user = User(
            email=f"odo-{suffix}@example.com",
            display_name="Odo Owner",
            hashed_password=hash_password("hunter22"),
            max_vehicles=3,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        vehicle = Vehicle(user_id=user.id, nickname="Odo Test", auto_suggest_service=True)
        db.add(vehicle)
        await db.commit()
        await db.refresh(vehicle)
        token = create_access_token(user.id)
        vehicle_id = vehicle.id
        # An upcoming service due at 20,000 km.
        db.add(ServiceRecord(
            vehicle_id=vehicle_id, service_date="2026-09-01", odometer_km=18000,
            service_type="scheduled", status="scheduled", next_due_km=20000,
        ))
        await db.commit()
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    return {"client": client, "token": token, "vehicle_id": vehicle_id}


async def _odo(db, vehicle_id: str) -> int:
    return (await db.get(Vehicle, vehicle_id)).odometer_km


@pytest.mark.asyncio
async def test_fuel_past_entry_cannot_roll_back_odo_and_suggests_service() -> None:
    world = await _setup()
    headers = {"Authorization": f"Bearer {world['token']}"}
    client: AsyncClient = world["client"]
    vid = world["vehicle_id"]
    base = f"/api/v1/vehicles/{vid}"

    # A newer fuel fill pushes the odo past the 20,000 km due threshold.
    resp = await client.post(
        f"{base}/fuel",
        json={"fill_date": "2026-08-01", "odometer_km": 25000,
              "litres": 50.0, "price_per_litre": 1.6, "total_cost": 80.0},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text

    async with SessionLocal() as db:
        assert await _odo(db, vid) == 25000
        events = list((await db.scalars(
            select(VehicleEvent).where(
                VehicleEvent.vehicle_id == vid,
                VehicleEvent.event_type == "service_due",
            )
        )).all())
        assert len(events) == 1, "one service_due suggestion expected"
        assert "due" in events[0].title

        # A past fuel receipt (lower reading) must NOT roll the odo back.
    await client.post(
        f"{base}/fuel",
        json={"fill_date": "2026-01-01", "odometer_km": 10000,
              "litres": 45.0, "price_per_litre": 1.6, "total_cost": 72.0},
        headers=headers,
    )
    async with SessionLocal() as db:
        assert await _odo(db, vid) == 25000
        events = list((await db.scalars(
            select(VehicleEvent).where(
                VehicleEvent.vehicle_id == vid,
                VehicleEvent.event_type == "service_due",
            )
        )).all())
        assert len(events) == 1, "suggestion must stay deduplicated"

    # A completed logbook trip (higher authority than fuel) advances the odo.
    started = await client.post(f"{base}/logbook", json={"started_at": "2026-08-02T09:00:00Z"}, headers=headers)
    assert started.status_code == 201, started.text
    done = await client.patch(
        f"{base}/logbook/{started.json()['id']}",
        json={"ended_at": "2026-08-02T10:00:00Z", "status": "completed", "end_odometer_km": 30000},
        headers=headers,
    )
    assert done.status_code == 200, done.text
    async with SessionLocal() as db:
        assert await _odo(db, vid) == 30000

    # A past logbook trip back-filled must not lower 30,000 either.
    await client.post(
        f"{base}/fuel",
        json={"fill_date": "2026-07-01", "odometer_km": 12000,
              "litres": 40.0, "price_per_litre": 1.7, "total_cost": 68.0},
        headers=headers,
    )
    async with SessionLocal() as db:
        assert await _odo(db, vid) == 30000

    await client.aclose()


@pytest.mark.asyncio
async def test_auto_suggest_off_creates_no_suggestion() -> None:
    suffix = uuid.uuid4().hex[:8]
    async with SessionLocal() as db:
        user = User(
            email=f"off-{suffix}@example.com", display_name="Off",
            hashed_password=hash_password("hunter22"), max_vehicles=3,
        )
        db.add(user)
        await db.commit()
        vehicle = Vehicle(user_id=user.id, nickname="No Suggest", auto_suggest_service=False)
        db.add(vehicle)
        await db.commit()
        token = create_access_token(user.id)
        vid = vehicle.id
        db.add(ServiceRecord(
            vehicle_id=vid, service_date="2026-09-01", odometer_km=18000,
            service_type="scheduled", status="scheduled", next_due_km=20000,
        ))
        await db.commit()
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    resp = await client.post(
        f"/api/v1/vehicles/{vid}/fuel",
        json={"fill_date": "2026-08-01", "odometer_km": 25000,
              "litres": 50.0, "price_per_litre": 1.6, "total_cost": 80.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    async with SessionLocal() as db:
        assert await _odo(db, vid) == 25000
        events = list((await db.scalars(
            select(VehicleEvent).where(
                VehicleEvent.vehicle_id == vid,
                VehicleEvent.event_type == "service_due",
            )
        )).all())
        assert len(events) == 0, "setting off must suppress suggestions"
    await client.aclose()


@pytest.mark.asyncio
async def test_no_scheduled_service_creates_next_from_history(monkeypatch) -> None:
    """Board note (AUT-1275 follow-up): when the odo is updated and no
    scheduled service exists, the last recorded services drive a prediction
    that creates the upcoming service with a due threshold."""
    async def _fake_predict(payload: dict) -> dict:
        return {
            "service_type": "scheduled",
            "interval_km": 10000,
            "interval_months": 6,
            "due_in_km": 0,
            "due_in_days": 0,
            "next_due_km": payload["last_service_km"] + 10000,
            "next_due_date": "2027-01-01",
            "confidence": 0.9,
            "reason": "from test history",
            "model": "rule-based-fallback",
        }
    import app.services.ai_client
    monkeypatch.setattr(app.services.ai_client, "predict_service", _fake_predict)

    suffix = uuid.uuid4().hex[:8]
    async with SessionLocal() as db:
        user = User(
            email=f"hist-{suffix}@example.com", display_name="Hist",
            hashed_password=hash_password("hunter22"), max_vehicles=3,
        )
        db.add(user)
        await db.commit()
        vehicle = Vehicle(user_id=user.id, nickname="Hist Car",
                          auto_suggest_service=True, odometer_km=50000)
        db.add(vehicle)
        await db.commit()
        # Past completed services — no scheduled service at all.
        db.add(ServiceRecord(
            vehicle_id=vehicle.id, service_date="2024-01-10", odometer_km=30000,
            service_type="scheduled", status="completed",
        ))
        db.add(ServiceRecord(
            vehicle_id=vehicle.id, service_date="2025-06-15", odometer_km=40000,
            service_type="scheduled", status="completed",
        ))
        await db.commit()
        token = create_access_token(user.id)
        vid = vehicle.id
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    resp = await client.post(
        f"/api/v1/vehicles/{vid}/fuel",
        json={"fill_date": "2026-08-01", "odometer_km": 52000,
              "litres": 50.0, "price_per_litre": 1.6, "total_cost": 80.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    async with SessionLocal() as db:
        assert await _odo(db, vid) == 52000
        created = list((await db.scalars(select(ServiceRecord).where(
            ServiceRecord.vehicle_id == vid, ServiceRecord.status == "scheduled",
        ))).all())
        assert len(created) == 1, "upcoming service should be auto-created"
        assert created[0].next_due_km == 50000, created[0].next_due_km
        assert created[0].ai_prediction == "from test history"
    await client.aclose()