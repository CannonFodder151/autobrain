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
from app.models.service import ServiceRecord
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
            max_vehicles=5,
        )
        db.add(demo)
        await db.flush()
        await _seed_demo_data(db, demo.id)
        await db.commit()
        logger.info("demo_seed_created", email=email)


async def _seed_demo_data(db, user_id: str) -> None:
    """Seed 5 demo vehicles (one standard daily driver) with ~6 years of data.

    Deterministic pseudo-random values (seeded) so the demo looks realistic but
    is identical on every fresh deployment.
    """
    import random

    rng = random.Random(7)
    today = date.today()

    # --- vehicle specs: (nickname, rego, make, model, year, engine, gearbox, odometer, condition, primary) ---
    specs = [
        ("Skyline R34", "GRN-34R", "Nissan", "Skyline GT-R", 2000,
         "RB26DETT", "Manual", 142000, "excellent", True),
        ("Family Commuter", "FAM-91Y", "Toyota", "Camry", 2020,
         "2.5L 4-cyl", "Automatic", 62000, "good", False),
        ("Weekend MX-5", "MX5-SKY", "Mazda", "MX-5", 2005,
         "1.8L BP", "Manual", 98000, "good", False),
        ("Tradie Hilux", "HLX-77T", "Toyota", "Hilux", 2016,
         "2.8L Turbo Diesel", "Manual", 184000, "fair", False),
        ("Project Silvia", "S15-PRO", "Nissan", "Silvia S15", 1999,
         "SR20DET", "Manual", 156000, "fair", False),
    ]
    # Fuel price path over 6 years (AUD/L): cheap -> expensive
    fuel_prices = [1.25, 1.31, 1.28, 1.42, 1.55, 1.63, 1.71, 1.78, 1.84, 1.91, 1.86, 1.94]

    vehicles = []
    for spec in specs:
        (nick, rego, make, model, year, engine, gb, odo, cond, primary) = spec
        v = Vehicle(
            user_id=user_id,
            nickname=nick, rego=rego, make=make, model=model, year=year,
            engine=engine, transmission=gb, odometer_km=odo,
            condition=cond, is_primary=primary,
        )
        db.add(v)
        await db.flush()
        vehicles.append(v)

    # --- 6 years of services, fuel, mods, parts for each vehicle ---
    for v, spec in zip(vehicles, specs):
        vid = v.id
        base_odo = spec[7]
        l100 = {  # typical L/100km per vehicle
            "Skyline R34": 12.2, "Family Commuter": 7.4, "Weekend MX-5": 8.1,
            "Tradie Hilux": 9.8, "Project Silvia": 11.3,
        }[spec[0]]

        # Fuel logs every ~4-5 weeks for 6 years (~72 fills)
        odo = base_odo - 62000
        last_odo = None
        for i in range(72):
            m = 72 - i
            fill_date = today - timedelta(days=int(m * 30.44))
            odo += rng.randint(450, 750)
            price = fuel_prices[min(i // 6, len(fuel_prices) - 1)]
            litres = round(l100 * (rng.randint(46, 72) / 10), 1)
            cost = round(litres * price, 2)
            dist = (odo - last_odo) if last_odo else None
            db.add(FuelLog(
                vehicle_id=vid, fill_date=fill_date, odometer_km=odo, litres=litres,
                price_per_litre=price, total_cost=cost, is_full_tank=True,
                distance_km=dist,
                l_per_100km=round(litres / (dist / 100), 1) if dist else None,
                cost_per_km=round(cost / dist, 3) if dist else None,
            ))
            last_odo = odo
            if i % 18 == 0:
                db.add(VehicleEvent(
                    vehicle_id=vid, event_type="fuel", title=f"Fuel fill {litres:.1f} L",
                    occurred_on=fill_date, odometer_km=odo, amount=cost,
                ))

        # ~1 service per year for 6 years, plus a few oil changes
        service_templates = {
            "Skyline R34": ["Major service + timing belt", "Brake pads & rotors", "Turbo rebuild"],
            "Family Commuter": ["Logbook service", "Brake pads", "Air-con regas", "Tyres"],
            "Weekend MX-5": ["Minor service", "Clutch kit", "Coilover install"],
            "Tradie Hilux": ["Full service", "Injector clean", "Clutch replacement", "Wheel bearing"],
            "Project Silvia": ["Major service", "Gearbox rebuild", "Turbo + fuel system"],
        }[spec[0]]
        for y in range(6):
            m = 6 - y
            svc_date = today - timedelta(days=int(m * 365) + rng.randint(0, 40))
            kind = rng.choice(["oil", "scheduled", "repair"])
            title = service_templates[y % len(service_templates)]
            cost = rng.choice([180, 320, 480, 650, 890, 1400, 2400])
            odo_at = base_odo - (6 - m) * rng.randint(9000, 13000)
            db.add(ServiceRecord(
                vehicle_id=vid, service_date=svc_date, odometer_km=max(odo_at, 0),
                service_type=kind, description=title, workshop="AutoBrain AutoWorks",
                cost=float(cost), status="completed",
            ))
            db.add(VehicleEvent(
                vehicle_id=vid, event_type="service", title=title,
                occurred_on=svc_date, odometer_km=max(odo_at, 0), amount=float(cost),
            ))

        # A couple of mods (performance cars) or accessories (standard car)
        mods = {
            "Skyline R34": [("Garrett GT2860R turbo upgrade", "performance", 4200),
                            ("Ohlins coilovers", "suspension", 3100),
                            ("Cusco strut brace", "performance", 420)],
            "Family Commuter": [("Roof racks", "exterior", 480),
                                ("Dash cam", "interior", 260),
                                ("All-weather mats", "interior", 150)],
            "Weekend MX-5": [("Enkei RPF1 wheels", "exterior", 2200),
                             ("Racing seat", "interior", 1400)],
            "Tradie Hilux": [("Canopy", "exterior", 2900),
                             ("ToughDog suspension", "suspension", 2600)],
            "Project Silvia": [("Garrett GT2871R turbo", "performance", 2900),
                               ("Nismo clutch", "performance", 950),
                               ("Bride bucket seat", "interior", 1300)],
        }[spec[0]]
        for (mname, cat, mcost), k in zip(mods, range(len(mods))):
            db.add(Modification(
                vehicle_id=vid, name=mname, category=cat, cost=float(mcost),
                install_date=today - timedelta(days=(len(mods) - k) * 300),
                odometer_km=base_odo - (len(mods) - k) * 8000,
                notes="Demo modification record.",
            ))
            db.add(VehicleEvent(
                vehicle_id=vid, event_type="mod", title=mname,
                occurred_on=today - timedelta(days=(len(mods) - k) * 300),
                odometer_km=base_odo - (len(mods) - k) * 8000, amount=float(mcost),
            ))

        # Parts inventory with low-stock example on the standard car
        parts = [("Engine oil filter", "OIL-FLT", "engine", 6, 2, 14.5),
                 ("Air filter", "AIR-FLT", "engine", 4, 2, 38.0),
                 ("Spark plugs (set)", "SPK-PLG", "engine", 8, 4, 62.0),
                 ("Brake pads (set)", "BRK-PAD", "brakes", 2, 1, 120.0)]
        if spec[0] == "Family Commuter":
            parts.append(("Washer fluid", "WSH-FLD", "other", 1, 3, 6.5))
        for (pname, sku, cat, qty, min_qty, ucost) in parts:
            db.add(Part(
                vehicle_id=vid, name=pname, sku=sku, category=cat,
                quantity=qty, min_quantity=min_qty, unit_cost=float(ucost),
                supplier="Repco", warranty_months=12,
            ))
