"""Seed utilities: bootstrap admin + demo account and sample data."""

import json
from datetime import date, timedelta

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.fuel import FuelLog
from app.models.mod import Modification
from app.models.part import Part
from app.models.service import ServiceItem, ServiceRecord
from app.models.user import User
from app.models.vehicle import Vehicle, VehicleEvent

logger = get_logger(__name__)


async def seed_admin() -> None:
    """Ensure the admin account from ADMIN_EMAIL/ADMIN_INITIAL_PASSWORD exists."""
    email = (settings.ADMIN_EMAIL or "").strip().lower()
    password = (settings.ADMIN_INITIAL_PASSWORD or "").strip()
    if not email or not password:
        logger.info("admin_seed_skipped_no_config")
        return
    async with SessionLocal() as db:
        existing = await db.scalar(select(User).where(User.email == email))
        if existing:
            logger.info("admin_seed_already_exists", email=email)
            return
        db.add(
            User(
                email=email,
                display_name=settings.ADMIN_DISPLAY_NAME,
                hashed_password=hash_password(password),
                role="admin",
            )
        )
        await db.commit()
        logger.info("admin_seed_created", email=email)


async def seed_demo() -> None:
    """Seed the read-only demo account + sample data when DEMO_MODE is on.

    The demo user has role='demo' which the API treats as read-only:
    every mutating endpoint and every AI module rejects it. This function is
    idempotent — existing demo data is left untouched across restarts.
    """
    if not settings.DEMO_MODE:
        return
    email = settings.DEMO_EMAIL.strip().lower()
    async with SessionLocal() as db:
        existing = await db.scalar(select(User).where(User.email == email))
        if existing:
            logger.info("demo_seed_already_exists", email=email)
            return
        demo = User(
            email=email,
            display_name=settings.DEMO_DISPLAY_NAME,
            hashed_password=hash_password(settings.DEMO_PASSWORD),
            role="demo",
            max_vehicles=2,
        )
        db.add(demo)
        await db.flush()
        await _seed_demo_data(db, demo.id)
        await db.commit()
        logger.info("demo_seed_created", email=email)


async def _seed_demo_data(db, user_id: str) -> None:
    today = date.today()
    # --- Vehicle 1: daily driver ---
    v1 = Vehicle(
        user_id=user_id,
        nickname="Skyline R34",
        rego="GRN-34R",
        vin="JN1GB32S70M000001",
        make="Nissan",
        model="Skyline GT-R",
        year=2000,
        engine="RB26DETT",
        transmission="Manual",
        odometer_km=142000,
        condition="excellent",
        is_primary=True,
    )
    db.add(v1)
    await db.flush()

    db.add(
        ServiceRecord(
            vehicle_id=v1.id,
            service_date=today - timedelta(days=30),
            odometer_km=140500,
            service_type="oil",
            description="Full synthetic oil + filter",
            workshop="AutoBrain AutoWorks",
            cost=185.0,
            status="completed",
            steps=json.dumps(["Drain oil", "Replace filter", "Refill 5W-30"]),
        )
    )
    db.add(
        ServiceRecord(
            vehicle_id=v1.id,
            service_date=today + timedelta(days=14),
            odometer_km=144000,
            service_type="scheduled",
            description="Brake fluid flush",
            cost=0.0,
            status="scheduled",
        )
    )
    db.add(
        FuelLog(
            vehicle_id=v1.id,
            fill_date=today - timedelta(days=5),
            odometer_km=141800,
            litres=58.2,
            price_per_litre=1.84,
            total_cost=107.09,
            is_full_tank=True,
            distance_km=480,
            l_per_100km=12.1,
            cost_per_km=0.223,
        )
    )
    db.add(
        FuelLog(
            vehicle_id=v1.id,
            fill_date=today - timedelta(days=17),
            odometer_km=141320,
            litres=57.9,
            price_per_litre=1.79,
            total_cost=103.64,
            is_full_tank=True,
            distance_km=472,
            l_per_100km=12.3,
            cost_per_km=0.220,
        )
    )
    db.add(
        Modification(
            vehicle_id=v1.id,
            name="Garrett GT2860R turbo upgrade",
            category="performance",
            brand="Garrett",
            cost=4200.0,
            install_date=today - timedelta(days=120),
            odometer_km=137000,
            notes="Twin turbo upgrade with ECU remap.",
        )
    )
    db.add(
        Modification(
            vehicle_id=v1.id,
            name="Coilover suspension",
            category="suspension",
            brand="Ohlins",
            cost=3100.0,
            install_date=today - timedelta(days=200),
            odometer_km=131000,
        )
    )
    db.add(
        Part(
            vehicle_id=v1.id,
            name="NGK BCPR7ES spark plugs",
            sku="NGK-BCPR7ES",
            category="engine",
            quantity=12,
            min_quantity=6,
            unit_cost=12.5,
            supplier="Repco",
            warranty_months=12,
        )
    )
    db.add(
        Part(
            vehicle_id=v1.id,
            name="RB26 oil filter",
            sku="OIL-RB26",
            category="engine",
            quantity=3,
            min_quantity=2,
            unit_cost=18.0,
            supplier="AutoBrain AutoWorks",
        )
    )

    # --- Vehicle 2: weekend toy ---
    v2 = Vehicle(
        user_id=user_id,
        nickname="RX-7 Spirit",
        rego="SPT-7R",
        make="Mazda",
        model="RX-7 FD",
        year=1996,
        engine="13B-REW",
        transmission="Manual",
        odometer_km=118000,
        condition="good",
    )
    db.add(v2)
    await db.flush()

    db.add(
        ServiceRecord(
            vehicle_id=v2.id,
            service_date=today - timedelta(days=60),
            odometer_km=116500,
            service_type="repair",
            description="Apex seal replacement + rebuild",
            workshop="Rotary Specialists",
            cost=6800.0,
            status="completed",
        )
    )
    db.add(
        FuelLog(
            vehicle_id=v2.id,
            fill_date=today - timedelta(days=2),
            odometer_km=118000,
            litres=45.0,
            price_per_litre=1.86,
            total_cost=83.7,
            is_full_tank=True,
            distance_km=290,
            l_per_100km=15.5,
            cost_per_km=0.289,
        )
    )
    db.add(
        Part(
            vehicle_id=v2.id,
            name="13B coolant seals kit",
            sku="13B-SEALS",
            category="engine",
            quantity=1,
            min_quantity=2,
            unit_cost=520.0,
            supplier="Rotary Specialists",
        )
    )

    # --- Timeline events so the unified timeline reads well ---
    db.add(
        VehicleEvent(
            vehicle_id=v1.id,
            event_type="service",
            title="Full synthetic oil + filter",
            occurred_on=today - timedelta(days=30),
            odometer_km=140500,
            amount=185.0,
        )
    )
    db.add(
        VehicleEvent(
            vehicle_id=v1.id,
            event_type="fuel",
            title="Fuel fill 58.2 L",
            occurred_on=today - timedelta(days=5),
            odometer_km=141800,
            amount=107.09,
        )
    )
    db.add(
        VehicleEvent(
            vehicle_id=v1.id,
            event_type="mod",
            title="Garrett GT2860R turbo upgrade",
            occurred_on=today - timedelta(days=120),
            odometer_km=137000,
            amount=4200.0,
        )
    )
    db.add(
        VehicleEvent(
            vehicle_id=v2.id,
            event_type="service",
            title="Apex seal replacement + rebuild",
            occurred_on=today - timedelta(days=60),
            odometer_km=116500,
            amount=6800.0,
        )
    )
