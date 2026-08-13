"""reset_demo must clear vehicle_shares before deleting the demo account (AUT-521).

A demo reset deletes the demo user + all demo vehicles. If a share references
a demo vehicle or the demo user, the FK (NO ACTION) blocks the deletes on
Postgres and the reset crashes at boot; on FK-less backends it leaves orphaned
shares. Regression: reset_demo removes those shares first.

Run (sqlite, no Postgres/MinIO needed):
    cd backend && python3 -m pytest tests/test_seed_reset_demo.py -q
"""

import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:////tmp/autobrain-seed-reset-test.db"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["DEMO_MODE"] = "true"
os.environ["DEMO_EMAIL"] = "demo@test.local"
os.environ["DEMO_PASSWORD"] = "demo"
os.environ["DEMO_DISPLAY_NAME"] = "Demo Garage"
os.environ["POSTGRES_USER"] = "autobrain"
os.environ["POSTGRES_PASSWORD"] = "autobrain"
os.environ["POSTGRES_DB"] = "autobrain"
os.environ["MINIO_ACCESS_KEY"] = "autobrain"
os.environ["MINIO_SECRET_KEY"] = "autobrain"
os.environ["MINIO_BUCKET"] = "autobrain-assets"
os.environ["MINIO_ENDPOINT"] = "minio:9000"
os.environ["AI_GATEWAY_API_KEY"] = "test-ai-key"
os.environ["ADMIN_API_KEY"] = "test-admin-key"
os.environ["MARKET_DATA_URL"] = ""
os.environ["MARKET_DATA_API_KEY"] = ""

import pytest  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.seed import _upload_demo_image, reset_demo, seed_demo  # noqa: E402
from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.models.share import VehicleShare  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.vehicle import Vehicle  # noqa: E402


async def _reset_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


@pytest.mark.asyncio
async def test_reset_demo_clears_shares(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.db.seed._upload_demo_image",
        lambda *a, **k: "https://minio.local/x.png",
    )
    await _reset_schema()
    await seed_demo()

    async with SessionLocal() as db:
        demo = await db.scalar(select(User).where(User.email == "demo@test.local"))
        demo_vehicle = await db.scalar(
            select(Vehicle).where(Vehicle.user_id == demo.id)
        )
        staff = User(
            email="staff@test.local",
            display_name="Staff",
            hashed_password=hash_password("hunter22"),
            max_vehicles=3,
        )
        db.add(staff)
        await db.flush()
        staff_vehicle = Vehicle(user_id=staff.id, nickname="Staff car")
        db.add(staff_vehicle)
        await db.flush()
        db.add_all(
            [
                VehicleShare(vehicle_id=demo_vehicle.id, invitee_user_id=staff.id),
                VehicleShare(vehicle_id=staff_vehicle.id, invitee_user_id=demo.id),
            ]
        )
        await db.commit()

    await reset_demo()

    async with SessionLocal() as db:
        count = await db.scalar(select(func.count()).select_from(VehicleShare))
        assert count == 0, "reset_demo left vehicle_shares behind"
        demo_after = await db.scalar(
            select(User).where(User.email == "demo@test.local")
        )
        assert demo_after is not None, "reset_demo failed to re-seed the demo user"
