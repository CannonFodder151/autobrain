"""Demo fuel-station seed regression (AUT-3162).

Servo Spy reads fuel_stations / fuel_prices, but the demo seed previously never
populated those tables — so /fuel/stations returned empty on demo. This test
asserts the demo seed now writes >=1 station with >=1 price per fuel type, and
that reset_demo wipes + re-seeds them cleanly (idempotent per reset cycle).

Run (sqlite, no Postgres/MinIO needed):
    cd backend && python3 -m pytest tests/test_demo_fuel_seed.py -q
"""

import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:////tmp/autobrain-seed-fuel-test.db"
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
os.environ["ADMIN_API_KEY"] = "test-admin-key-0123456789-0123456789"
os.environ["MARKET_DATA_URL"] = ""
os.environ["MARKET_DATA_API_KEY"] = ""

import pytest  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.seed import reset_demo, seed_demo  # noqa: E402
from app.db.session import Base  # noqa: E402
from app.models.fuel_station import FuelPrice, FuelPriceArbitration, FuelStation  # noqa: E402
from app.models.user import User  # noqa: E402

settings.DEMO_MODE = True
settings.DEMO_EMAIL = "demo@test.local"
settings.DEMO_PASSWORD = "demo"
settings.DEMO_DISPLAY_NAME = "Demo Garage"

engine = create_async_engine("sqlite+aiosqlite:////tmp/autobrain-seed-fuel-test.db")
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

import app.db.seed as seed_module  # noqa: E402

seed_module.SessionLocal = SessionLocal

EXPECTED_FUEL_TYPES = {"91", "95", "98", "E10", "Diesel", "LPG"}


async def _reset_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


@pytest.mark.asyncio
async def test_demo_seed_populates_fuel_stations(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.db.seed._upload_demo_image",
        lambda *a, **k: "https://minio.local/x.png",
    )
    await _reset_schema()
    await seed_demo()
    async with SessionLocal() as db:
        stations = list((await db.scalars(
            select(FuelStation).where(FuelStation.source == "demo")
        )).all())
        assert len(stations) >= 1, "expected >=1 demo fuel stations"
        for s in stations:
            assert s.source_id.startswith("demo-")
            assert s.brand and s.lat is not None and s.lon is not None

        types = set((await db.scalars(
            select(FuelPrice.fuel_type).where(FuelPrice.station_id.in_([s.id for s in stations]))
        )).all())
        assert EXPECTED_FUEL_TYPES.issubset(types), f"missing fuel types: {EXPECTED_FUEL_TYPES - types}"

        for s in stations:
            prices = list((await db.scalars(
                select(FuelPrice).where(FuelPrice.station_id == s.id)
            )).all())
            assert len(prices) >= 1, f"station {s.name} has no prices"
            arb = await db.scalar(
                select(func.count()).select_from(FuelPriceArbitration).where(
                    FuelPriceArbitration.station_id == s.id
                )
            )
            assert arb == len(EXPECTED_FUEL_TYPES), "arbitration rows missing per fuel type"


@pytest.mark.asyncio
async def test_fuel_seed_is_idempotent_per_reset_cycle(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.db.seed._upload_demo_image",
        lambda *a, **k: "https://minio.local/x.png",
    )
    await _reset_schema()
    await seed_demo()
    async with SessionLocal() as db:
        first = await db.scalar(select(func.count()).select_from(FuelStation).where(FuelStation.source == "demo"))
    # Calling seed_demo again (user already exists) must NOT duplicate.
    await seed_demo()
    async with SessionLocal() as db:
        again = await db.scalar(select(func.count()).select_from(FuelStation).where(FuelStation.source == "demo"))
    assert again == first, "seed_demo duplicated fuel stations on second call"

    # reset_demo wipes them, then re-seeds.
    await reset_demo()
    async with SessionLocal() as db:
        wiped = await db.scalar(select(func.count()).select_from(FuelStation).where(FuelStation.source == "demo"))
        prices = await db.scalar(select(func.count()).select_from(FuelPrice).where(FuelPrice.station_id.in_(
            [s.id for s in (await db.scalars(select(FuelStation).where(FuelStation.source == "demo"))).all()]
        )))
        assert wiped >= 1, "reset_demo wiped demo stations"
        assert prices >= 1, "reset_demo re-seeded demo prices"


@pytest.mark.asyncio
async def test_demo_user_can_access_fuel_via_free_flag(monkeypatch) -> None:
    """The demo user must pass the premium gate (free_account=False)."""
    monkeypatch.setattr(
        "app.db.seed._upload_demo_image",
        lambda *a, **k: "https://minio.local/x.png",
    )
    await _reset_schema()
    await seed_demo()
    async with SessionLocal() as db:
        demo = await db.scalar(select(User).where(User.email == "demo@test.local"))
        assert demo is not None
        assert demo.free_account is False, "demo user must have fuel access"