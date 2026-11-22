"""AUT-734: PHEV dual-source tracking service tests (DB-backed with SQLite).

Tests the compute_phev_dashboard, compute_phev_timeline, and export_phev_csv
functions with real fuel logs + EV trips against an in-memory SQLite database.
"""

import os
import tempfile
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.session import Base
from app.models import (
    Vehicle,
    FuelLog,
    LogEntry,
    User,
)
from app.services import phev as phev_svc


# Use a unique temp SQLite file per run to avoid schema conflicts across CI runs.
_db_fd, _db_path = tempfile.mkstemp(suffix=".db", prefix="autobrain-phev-test-")
os.close(_db_fd)
os.unlink(_db_path)
_DB_URL = f"sqlite+aiosqlite:///{_db_path}"

engine = create_async_engine(_DB_URL)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _mock_ai(*args, **kwargs):
    """Mock AI gateway: always returns None so the deterministic fallback runs."""
    return None


async def _reset_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


async def _make_user(db: AsyncSession, **kw) -> User:
    u = User(
        id=kw.get("id", "u1"),
        email=kw.get("email", "test@example.com"),
        display_name=kw.get("display_name", "Test User"),
        hashed_password=kw.get("hashed_password", "x"),
        free_account=kw.get("free_account", False),
    )
    db.add(u)
    await db.flush()
    return u


async def _make_vehicle(db: AsyncSession, user_id: str, **kw) -> Vehicle:
    v = Vehicle(
        id=kw.get("id", "v1"),
        user_id=user_id,
        nickname=kw.get("nickname", "Test PHEV"),
        powertrain=kw.get("powertrain", "PHEV"),
        odometer_km=kw.get("odometer_km", 0),
    )
    db.add(v)
    await db.flush()
    return v


async def _make_fuel_log(db: AsyncSession, vehicle_id: str, **kw) -> FuelLog:
    log = FuelLog(
        vehicle_id=vehicle_id,
        fill_date=kw.get("fill_date", date.today()),
        odometer_km=kw.get("odometer_km", 0),
        litres=kw.get("litres", 0),
        price_per_litre=kw.get("price_per_litre", 1.0),
        total_cost=kw.get("total_cost", 0),
        distance_km=kw.get("distance_km"),
        is_full_tank=kw.get("is_full_tank", True),
    )
    db.add(log)
    await db.flush()
    return log


async def _make_ev_trip(db: AsyncSession, vehicle_id: str, **kw) -> LogEntry:
    trip = LogEntry(
        vehicle_id=vehicle_id,
        started_at=kw.get("started_at", datetime.now(timezone.utc)),
        ended_at=kw.get("ended_at", datetime.now(timezone.utc)),
        distance_km=kw.get("distance_km"),
        ev_distance_km=kw.get("ev_distance_km"),
        ice_distance_km=kw.get("ice_distance_km"),
        charge_added_kwh=kw.get("charge_added_kwh"),
        vehicle_type=kw.get("vehicle_type", "phev"),
        status="completed",
        source=kw.get("source", "manual"),
    )
    db.add(trip)
    await db.flush()
    return trip


@pytest.mark.asyncio
async def test_compute_phev_dashboard_combines_fuel_and_ev_data(monkeypatch) -> None:
    """Dashboard aggregates fuel logs + EV trips into combined MPGe, cost/km, etc."""
    monkeypatch.setattr("app.services.phev.run_advisor_ai", _mock_ai)
    await _reset_schema()

    async with SessionLocal() as db:
        user = await _make_user(db, id="u1")
        vehicle = await _make_vehicle(db, user_id=user.id, id="v1", powertrain="PHEV")

        # Fuel logs: 2 full-tank fills, 80 L total, 700 km chained distance
        today = date.today()
        await _make_fuel_log(
            db,
            vehicle.id,
            fill_date=today - timedelta(days=10),
            odometer_km=1000,
            litres=40,
            price_per_litre=1.50,
            total_cost=60.0,
            distance_km=300,
        )
        await _make_fuel_log(
            db,
            vehicle.id,
            fill_date=today - timedelta(days=5),
            odometer_km=1400,
            litres=40,
            price_per_litre=1.50,
            total_cost=60.0,
            distance_km=400,
        )

        # EV trips: 2 trips, 150 km EV, 50 km ICE, 33 kWh total charge
        await _make_ev_trip(
            db,
            vehicle.id,
            started_at=datetime(
                today.year, today.month, today.day - 8, tzinfo=timezone.utc
            ),
            distance_km=100,
            ev_distance_km=60,
            ice_distance_km=40,
            charge_added_kwh=15,
        )
        await _make_ev_trip(
            db,
            vehicle.id,
            started_at=datetime(
                today.year, today.month, today.day - 3, tzinfo=timezone.utc
            ),
            distance_km=100,
            ev_distance_km=90,
            ice_distance_km=10,
            charge_added_kwh=18,
        )
        await db.commit()

        dash = await phev_svc.compute_phev_dashboard(db, vehicle.id, period_days=365)

        # --- Distance ---
        assert dash.distance.ev_km == pytest.approx(150.0)
        assert dash.distance.ice_km == pytest.approx(750.0)  # 700 fuel + 50 trip ICE
        assert dash.distance.total_km == pytest.approx(900.0)
        assert dash.distance.ev_ratio == pytest.approx(
            0.167, rel=1e-3
        )  # 150/900 rounded to 3dp

        # --- Energy ---
        assert dash.energy.fuel_litres == pytest.approx(80.0)
        assert dash.energy.fuel_cost == pytest.approx(120.0)
        assert dash.energy.charge_kwh == pytest.approx(33.0)
        assert dash.energy.electricity_cost == pytest.approx(33 * 0.30, rel=1e-3)
        assert dash.energy.total_cost == pytest.approx(120.0 + 9.90, rel=1e-3)

        # --- Efficiency ---
        # fuel L/100km = 80 / 700 * 100 = 11.43
        assert dash.efficiency.fuel_l_per_100km == pytest.approx(11.43, rel=1e-2)
        # EV kWh/100km = 33 / 150 * 100 = 22.0
        assert dash.efficiency.ev_kwh_per_100km == pytest.approx(22.0, rel=1e-2)
        # Combined L/100km equiv ≈ 9.3
        assert dash.efficiency.combined_l_per_100km_equiv is not None
        assert dash.efficiency.combined_l_per_100km_equiv == pytest.approx(
            9.3, rel=0.05
        )
        # MPGe ≈ 25.3
        assert dash.efficiency.combined_mpge is not None
        assert dash.efficiency.combined_mpge == pytest.approx(25.3, rel=0.05)

        # --- Cost ---
        assert dash.cost.cost_per_km == pytest.approx(129.90 / 900, rel=1e-3)
        assert dash.cost.cost_per_mile is not None
        assert dash.cost.cost_per_mile == pytest.approx(
            129.90 / 900 * 1.609344, rel=1e-3
        )

        # --- Sources ---
        assert dash.sources["fuel_logs"] == 2
        assert dash.sources["ev_trips"] == 2

        # --- AI insights (deterministic fallback) ---
        assert len(dash.ai_insights) >= 1
        titles = [i.title for i in dash.ai_insights]
        assert "ICE is doing most of the work" in titles  # ice_km > ev_km
        assert any(i.type == "savings" for i in dash.ai_insights)


@pytest.mark.asyncio
async def test_compute_phev_dashboard_empty_vehicle(monkeypatch) -> None:
    """Dashboard returns zeros and a guidance insight when no data exists."""
    monkeypatch.setattr("app.services.phev.run_advisor_ai", _mock_ai)
    await _reset_schema()

    async with SessionLocal() as db:
        user = await _make_user(db, id="u2")
        vehicle = await _make_vehicle(db, user_id=user.id, id="v2", powertrain="PHEV")
        await db.commit()

        dash = await phev_svc.compute_phev_dashboard(db, vehicle.id, period_days=365)

        assert dash.distance.total_km == 0
        assert dash.distance.ev_km == 0
        assert dash.distance.ice_km == 0
        assert dash.energy.fuel_litres == 0
        assert dash.energy.charge_kwh == 0
        assert dash.energy.total_cost == 0
        assert dash.efficiency.fuel_l_per_100km is None
        assert dash.efficiency.ev_kwh_per_100km is None
        assert dash.efficiency.combined_mpge is None
        assert dash.cost.cost_per_km is None

        # Insight: "Start logging trips"
        assert len(dash.ai_insights) == 1
        assert dash.ai_insights[0].title == "Start logging trips"


@pytest.mark.asyncio
async def test_compute_phev_dashboard_non_phev_vehicle(monkeypatch) -> None:
    """Non-PHEV vehicles get a 'Not a PHEV' insight."""
    monkeypatch.setattr("app.services.phev.run_advisor_ai", _mock_ai)
    await _reset_schema()

    async with SessionLocal() as db:
        user = await _make_user(db, id="u3")
        vehicle = await _make_vehicle(db, user_id=user.id, id="v3", powertrain="ICE")
        await db.commit()

        dash = await phev_svc.compute_phev_dashboard(db, vehicle.id, period_days=365)

        assert dash.powertrain == "ICE"
        assert any(i.title == "Not a PHEV" for i in dash.ai_insights)


@pytest.mark.asyncio
async def test_compute_phev_timeline_unifies_fuel_and_ev() -> None:
    """Timeline merges fuel fill-ups and completed EV/ICE trips, newest first."""
    await _reset_schema()

    async with SessionLocal() as db:
        user = await _make_user(db, id="u4")
        vehicle = await _make_vehicle(db, user_id=user.id, id="v4", powertrain="PHEV")

        today = date.today()
        # Fuel: 2 fills
        f1 = await _make_fuel_log(
            db,
            vehicle.id,
            fill_date=today - timedelta(days=5),
            odometer_km=1000,
            litres=40,
            price_per_litre=1.5,
            total_cost=60,
        )
        f2 = await _make_fuel_log(
            db,
            vehicle.id,
            fill_date=today - timedelta(days=10),
            odometer_km=800,
            litres=30,
            price_per_litre=1.5,
            total_cost=45,
        )

        # EV trips: 2 completed
        t1 = await _make_ev_trip(
            db,
            vehicle.id,
            started_at=datetime(
                today.year, today.month, today.day - 2, tzinfo=timezone.utc
            ),
            distance_km=50,
            ev_distance_km=50,
            ice_distance_km=0,
            charge_added_kwh=12,
        )
        t2 = await _make_ev_trip(
            db,
            vehicle.id,
            started_at=datetime(
                today.year, today.month, today.day - 7, tzinfo=timezone.utc
            ),
            distance_km=60,
            ev_distance_km=30,
            ice_distance_km=30,
            charge_added_kwh=8,
        )
        await db.commit()

        timeline = await phev_svc.compute_phev_timeline(db, vehicle.id)

        assert len(timeline.events) == 4
        # Newest first: EV trip (2 days ago) -> Fuel (5 days) -> EV trip (7 days) -> Fuel (10 days)
        assert timeline.events[0].id == t1.id
        assert timeline.events[0].event_type == "ev_trip"
        assert timeline.events[1].id == f1.id
        assert timeline.events[1].event_type == "fuel"
        assert timeline.events[2].id == t2.id
        assert timeline.events[2].event_type == "ev_trip"
        assert timeline.events[3].id == f2.id
        assert timeline.events[3].event_type == "fuel"

        # Fuel event has litres, cost
        assert timeline.events[1].litres == 40
        assert timeline.events[1].amount == 60

        # EV trip has EV/ICE split, charge
        assert timeline.events[0].ev_distance_km == 50
        assert timeline.events[0].ice_distance_km == 0
        assert timeline.events[0].charge_kwh == 12


@pytest.mark.asyncio
async def test_export_phev_csv_content() -> None:
    """CSV export contains fuel section + EV trip section with correct columns."""
    await _reset_schema()

    async with SessionLocal() as db:
        user = await _make_user(db, id="u5")
        vehicle = await _make_vehicle(
            db, user_id=user.id, id="v5", nickname="Test PHEV", powertrain="PHEV"
        )

        today = date.today()
        await _make_fuel_log(
            db,
            vehicle.id,
            fill_date=today,
            odometer_km=1500,
            litres=50,
            price_per_litre=1.60,
            total_cost=80,
        )
        await _make_ev_trip(
            db,
            vehicle.id,
            started_at=datetime(
                today.year, today.month, today.day, tzinfo=timezone.utc
            ),
            distance_km=80,
            ev_distance_km=60,
            ice_distance_km=20,
            charge_added_kwh=14,
        )
        await db.commit()

        csv_bytes = phev_svc.export_phev_csv(vehicle.id, vehicle.nickname, [], [])

        # Empty lists -> just headers
        text = csv_bytes.decode("utf-8-sig")  # handle BOM
        assert "AutoBrain PHEV Dual-Source Report" in text
        assert "--- ICE fuel fill-ups ---" in text
        assert "--- EV / PHEV trips ---" in text

        # With data
        fuel_logs = list(
            (
                await db.scalars(
                    select(FuelLog).where(FuelLog.vehicle_id == vehicle.id)
                )
            ).all()
        )
        ev_trips = list(
            (
                await db.scalars(
                    select(LogEntry).where(LogEntry.vehicle_id == vehicle.id)
                )
            ).all()
        )
        csv_bytes2 = phev_svc.export_phev_csv(
            vehicle.id, vehicle.nickname, fuel_logs, ev_trips
        )
        text2 = csv_bytes2.decode("utf-8-sig")
        assert "80" in text2  # total_cost
        assert "1.6" in text2  # price/l (csv writer strips trailing zeros)
        assert "60" in text2  # ev_distance_km
        assert "20" in text2  # ice_distance_km
        assert "14" in text2  # charge_added_kwh


@pytest.mark.asyncio
async def test_build_phev_export_returns_metadata_and_bytes() -> None:
    """build_phev_export wraps CSV bytes with filename/size metadata."""
    await _reset_schema()

    async with SessionLocal() as db:
        user = await _make_user(db, id="u6")
        vehicle = await _make_vehicle(
            db, user_id=user.id, id="v6", nickname="Export PHEV"
        )
        await db.commit()

        meta, csv_bytes = await phev_svc.build_phev_export(
            db, vehicle.id, vehicle.nickname
        )

        assert meta.filename == "phev-Export-PHEV.csv"
        assert meta.content_type == "text/csv"
        assert meta.size_bytes == len(csv_bytes)
        assert csv_bytes.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM


@pytest.mark.asyncio
async def test_mpge_calculation_math() -> None:
    """Direct unit test of the MPGe helper (no DB needed)."""
    # 100 km, 10 L fuel, 20 kWh charge
    # fuel gallons = 10 / 3.78541 = 2.6417
    # ev gallons eq = 20 / 33.7 = 0.5935
    # total = 3.2352
    # miles = 100 / 1.609344 = 62.137
    # MPGe = 62.137 / 3.2352 = 19.2
    from app.services.phev import _compute_mpge

    mpge = _compute_mpge(distance_km=100.0, fuel_litres=10.0, charge_kwh=20.0)
    assert mpge == pytest.approx(19.2, rel=0.02)

    # Zero energy -> None
    assert _compute_mpge(100.0, 0.0, 0.0) is None
    # Zero distance -> None
    assert _compute_mpge(0.0, 10.0, 20.0) is None
    # Fuel only -> standard MPG
    assert _compute_mpge(100.0, 10.0, 0.0) == pytest.approx(
        62.137 / (10.0 / 3.78541), rel=1e-3
    )


@pytest.mark.asyncio
async def test_combined_l_per_100km_equiv_math() -> None:
    """Unit test of the combined L/100km equivalent helper."""
    from app.services.phev import _combined_l_per_100km_equiv

    # 100 km, 10 L fuel, 33.7 kWh (exactly 1 gallon eq = 3.78541 L eq)
    # total L eq = 10 + 3.78541 = 13.78541
    # L/100km = 13.78541
    val = _combined_l_per_100km_equiv(100.0, 10.0, 33.7)
    assert val == pytest.approx(13.79, rel=1e-3)  # helper rounds to 2 dp

    assert _combined_l_per_100km_equiv(100.0, 0.0, 0.0) is None
    assert _combined_l_per_100km_equiv(0.0, 10.0, 20.0) is None


# Cleanup temp DB file after the test module finishes
def pytest_sessionfinish(session, exitstatus):
    try:
        if os.path.exists(_db_path):
            os.unlink(_db_path)
    except OSError:
        pass
