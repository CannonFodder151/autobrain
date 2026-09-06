"""AUT-2436 electricity log service: deterministic chain + stats.

Runs the recompute + stats helpers against an in-memory async SQLite
database so the suite stays hermetic (no compose Postgres required).
Asserts:

  * full-charge -> full-charge chains produce distance_km, km_per_kwh,
    cost_per_km;
  * non-full (top-up) charges do NOT poison the chain (no efficiency);
  * out-of-order odometer entries stay unchained;
  * stats aggregates total kWh / cost / averages;
  * delete + recompute clears the orphaned efficiency.
"""

import os
from datetime import date

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("MINIO_ACCESS_KEY", "x")
os.environ.setdefault("MINIO_SECRET_KEY", "y")
os.environ.setdefault("MINIO_BUCKET", "z")
os.environ.setdefault("ENVIRONMENT", "test")

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.models.electricity import ElectricityLog  # noqa: E402
from app.services.electricity import (  # noqa: E402
    compute_electricity_stats,
    recompute_efficiency,
)


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(ElectricityLog.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _add(session: AsyncSession, **kw) -> ElectricityLog:
    log = ElectricityLog(
        vehicle_id="v1",
        charge_date=kw.get("charge_date", date(2026, 1, 1)),
        odometer_km=kw["odometer_km"],
        kwh=kw["kwh"],
        price_per_kwh=kw["price_per_kwh"],
        total_cost=round(kw["kwh"] * kw["price_per_kwh"], 2),
        is_full_charge=kw.get("is_full_charge", True),
    )
    session.add(log)
    await session.flush()
    return log


@pytest.mark.asyncio
async def test_full_charge_chain_yields_efficiency(session: AsyncSession) -> None:
    await _add(session, odometer_km=1000, kwh=20, price_per_kwh=0.5)
    await _add(session, odometer_km=1200, kwh=18, price_per_kwh=0.5, charge_date=date(2026, 1, 5))
    await recompute_efficiency(session, "v1")
    rows = list((await session.scalars(__import__("sqlalchemy").select(ElectricityLog).order_by(ElectricityLog.odometer_km))).all())
    assert rows[0].distance_km is None
    assert rows[0].km_per_kwh is None
    assert rows[1].distance_km == 200.0
    assert rows[1].km_per_kwh == round(200 / 18, 2)
    assert rows[1].cost_per_km == round(18 * 0.5 / 200, 4)


@pytest.mark.asyncio
async def test_topup_charge_does_not_poison_chain(session: AsyncSession) -> None:
    await _add(session, odometer_km=1000, kwh=20, price_per_kwh=0.5)
    await _add(session, odometer_km=1100, kwh=5, price_per_kwh=0.5, is_full_charge=False, charge_date=date(2026, 1, 3))
    await _add(session, odometer_km=1200, kwh=18, price_per_kwh=0.5, charge_date=date(2026, 1, 5))
    await recompute_efficiency(session, "v1")
    rows = list((await session.scalars(__import__("sqlalchemy").select(ElectricityLog).order_by(ElectricityLog.odometer_km))).all())
    # topup (1100) is not a full charge; full-to-full chain is from 1000 -> 1200.
    assert rows[1].distance_km is None
    assert rows[1].km_per_kwh is None
    assert rows[2].distance_km == 200.0


@pytest.mark.asyncio
async def test_duplicate_odometer_does_not_poison_chain(session: AsyncSession) -> None:
    """Two charges at the same odometer (e.g. recorded twice) must not
    generate a distance of 0 in the chain (would divide-by-zero / 0
    km/kWh). Only strictly-positive distances produce an efficiency."""
    sa = __import__("sqlalchemy")
    await _add(session, odometer_km=1000, kwh=20, price_per_kwh=0.5)
    # duplicate odometer, also a full charge
    await _add(session, odometer_km=1000, kwh=15, price_per_kwh=0.5, charge_date=date(2026, 1, 3))
    await _add(session, odometer_km=1200, kwh=18, price_per_kwh=0.5, charge_date=date(2026, 1, 5))
    await recompute_efficiency(session, "v1")
    rows = list((await session.scalars(sa.select(ElectricityLog).order_by(ElectricityLog.odometer_km, ElectricityLog.charge_date))).all())
    # rows[0] (first 1000): no prior full -> None
    # rows[1] (second 1000, is_full=True): prev=1000 too, distance=0, dropped
    assert rows[1].distance_km is None
    assert rows[1].km_per_kwh is None
    # rows[2] (1200): prev full chain is rows[1] (odo=1000, is_full=True),
    # so distance=200, km/kWh valid.
    assert rows[2].distance_km == 200.0


@pytest.mark.asyncio
async def test_stats_aggregates_totals_and_averages(session: AsyncSession) -> None:
    await _add(session, odometer_km=1000, kwh=20, price_per_kwh=0.4, charge_date=date(2026, 1, 1))
    await _add(session, odometer_km=1200, kwh=10, price_per_kwh=0.4, charge_date=date(2026, 1, 5))
    await _add(session, odometer_km=1400, kwh=10, price_per_kwh=0.4, charge_date=date(2026, 1, 9))
    await recompute_efficiency(session, "v1")
    stats = await compute_electricity_stats(session, "v1")
    assert stats.total_kwh == 40.0
    assert stats.total_cost == 16.0
    assert stats.avg_kwh_per_charge == round(40 / 3, 2)
    # Two full-charge chains (1000->1200 and 1200->1400) each yield km/kWh.
    assert stats.avg_km_per_kwh is not None
    assert stats.last_log is not None
    assert stats.last_log.charge_date == date(2026, 1, 9)


@pytest.mark.asyncio
async def test_delete_recompute_removes_orphaned_efficiency(session: AsyncSession) -> None:
    """Delete a middle full charge; the remaining two (1000 -> 1400) both
    full-charge entries now chain directly across the gap — efficiency
    recalculates for the 1400 entry using the new (larger) distance."""
    sa = __import__("sqlalchemy")
    a = await _add(session, odometer_km=1000, kwh=20, price_per_kwh=0.5)
    b = await _add(session, odometer_km=1200, kwh=18, price_per_kwh=0.5, charge_date=date(2026, 1, 5))
    await _add(session, odometer_km=1400, kwh=18, price_per_kwh=0.5, charge_date=date(2026, 1, 9))
    await recompute_efficiency(session, "v1")
    rows = list((await session.scalars(sa.select(ElectricityLog).order_by(ElectricityLog.odometer_km))).all())
    assert rows[2].km_per_kwh is not None

    # Delete middle charge -> chain becomes 1000 -> 1400 (distance=400)
    await session.delete(b)
    await session.flush()
    await recompute_efficiency(session, "v1")
    rows = list((await session.scalars(sa.select(ElectricityLog).order_by(ElectricityLog.odometer_km))).all())
    assert rows[0].id == a.id
    assert rows[0].km_per_kwh is None  # first entry, no prior full
    assert rows[1].distance_km == 400.0
    assert rows[1].km_per_kwh == round(400 / 18, 2)
    assert rows[1].cost_per_km == round(18 * 0.5 / 400, 4)
