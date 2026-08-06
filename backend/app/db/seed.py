"""Seed utilities: bootstrap admin + demo account and sample data."""

import asyncio
import io
import json
import struct
import zlib
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import hash_password
from app.core.storage import ensure_bucket, upload_object
from app.db.session import SessionLocal
from app.models.diagnostic import Diagnostic
from app.models.fuel import FuelLog
from app.models.logbook import LogEntry
from app.models.mod import Modification
from app.models.notification import NotificationDelivery, NotificationPreference
from app.models.obd import ObdCode
from app.models.part import Part
from app.models.receipt import ExtractedItem, Receipt
from app.models.service import ServiceItem, ServiceRecord
from app.models.user import User
from app.models.valuation import ValuationSnapshot
from app.models.vehicle import Vehicle, VehicleEvent

logger = get_logger(__name__)


def _png_bytes(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    """Build a minimal valid PNG (solid colour) with stdlib only."""

    def chunk(typ: bytes, data: bytes) -> bytes:
        body = typ + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


async def _upload_demo_image(key: str, rgb: tuple[int, int, int]) -> str:
    """Upload a small generated PNG to MinIO and return its public URL."""
    await ensure_bucket()
    return await upload_object(key, _png_bytes(640, 420, rgb), "image/png")


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
            max_vehicles=8,
        )
        db.add(demo)
        await db.flush()
        await _seed_demo_data(db, demo.id)
        await db.commit()
        logger.info("demo_seed_created", email=email)


async def reset_demo() -> None:
    """Delete the demo user + all demo data, then re-seed.

    Used when the seed changes (new features) so an existing demo instance
    gets the current sample data. Triggered by DEMO_RESET=true on startup.
    """
    from sqlalchemy import delete

    if not settings.DEMO_MODE:
        return
    email = settings.DEMO_EMAIL.strip().lower()
    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.email == email))
        if not user:
            logger.info("demo_reset_no_user", email=email)
        else:
            vids = list((await db.scalars(
                select(Vehicle.id).where(Vehicle.user_id == user.id)
            )).all())
            if vids:
                svc_ids = list((await db.scalars(
                    select(ServiceRecord.id).where(ServiceRecord.vehicle_id.in_(vids))
                )).all())
                rcp_ids = list((await db.scalars(
                    select(Receipt.id).where(Receipt.vehicle_id.in_(vids))
                )).all())
                for v in vids:
                    await db.execute(delete(FuelLog).where(FuelLog.vehicle_id == v))
                    await db.execute(delete(Modification).where(Modification.vehicle_id == v))
                    await db.execute(delete(Part).where(Part.vehicle_id == v))
                    await db.execute(delete(LogEntry).where(LogEntry.vehicle_id == v))
                    await db.execute(delete(Diagnostic).where(Diagnostic.vehicle_id == v))
                    await db.execute(delete(ValuationSnapshot).where(ValuationSnapshot.vehicle_id == v))
                    await db.execute(delete(NotificationPreference).where(NotificationPreference.vehicle_id == v))
                    await db.execute(delete(NotificationDelivery).where(NotificationDelivery.vehicle_id == v))
                    await db.execute(delete(ObdCode).where(ObdCode.vehicle_id == v))
                    await db.execute(delete(VehicleEvent).where(VehicleEvent.vehicle_id == v))
                if svc_ids:
                    await db.execute(delete(ServiceItem).where(ServiceItem.service_id.in_(svc_ids)))
                await db.execute(delete(ServiceRecord).where(ServiceRecord.vehicle_id.in_(vids)))
                if rcp_ids:
                    await db.execute(delete(ExtractedItem).where(ExtractedItem.receipt_id.in_(rcp_ids)))
                await db.execute(delete(Receipt).where(Receipt.vehicle_id.in_(vids)))
                await db.execute(delete(Vehicle).where(Vehicle.user_id == user.id))
            await db.execute(delete(User).where(User.id == user.id))
            await db.commit()
            logger.info("demo_reset_deleted", user=user.id)
    await seed_demo()


async def _seed_demo_data(db, user_id: str) -> None:
    """Seed 5 demo vehicles (one standard daily driver) with ~6 years of data.

    Deterministic pseudo-random values (seeded) so the demo looks realistic but
    is identical on every fresh deployment.
    """
    import random

    rng = random.Random(7)
    today = date.today()

    # --- vehicle specs: (nickname, rego, make, model, year, engine, gearbox, odometer, condition, primary, colour, body_type, club_reg, vehicle_type) ---
    specs = [
        ("Skyline R34", "GRN-34R", "Nissan", "Skyline GT-R", 2000,
         "RB26DETT", "Manual", 142000, "excellent", True, "Bayside Blue", "Coupe", False, "car"),
        ("Family Commuter", "FAM-91Y", "Toyota", "Camry", 2020,
         "2.5L 4-cyl", "Automatic", 62000, "good", False, "Silver", "Sedan", False, "car"),
        ("Weekend MX-5", "MX5-SKY", "Mazda", "MX-5", 2005,
         "1.8L BP", "Manual", 98000, "good", False, "Classic Red", "Convertible", False, "car"),
        ("Tradie Hilux", "HLX-77T", "Toyota", "Hilux", 2016,
         "2.8L Turbo Diesel", "Manual", 184000, "fair", False, "White", "Utility", False, "car"),
        ("Project Silvia", "S15-PRO", "Nissan", "Silvia S15", 1999,
         "SR20DET", "Manual", 156000, "fair", False, "Pearl White", "Coupe", True, "car"),
        ("Ducati Monster", "MSTR-72", "Ducati", "Monster 821", 2019,
         "821cc L-Twin", "Manual", 28000, "excellent", False, "Red", "Naked", False, "motorcycle"),
        ("Kawasaki Ninja", "NJA-19K", "Kawasaki", "Ninja 650", 2021,
         "649cc Parallel-Twin", "Manual", 12000, "excellent", False, "Green", "Sport", False, "motorcycle"),
    ]
    # Fuel price path over 6 years (AUD/L): cheap -> expensive
    fuel_prices = [1.25, 1.31, 1.28, 1.42, 1.55, 1.63, 1.71, 1.78, 1.84, 1.91, 1.86, 1.94]

    vehicles = []
    for spec in specs:
        (nick, rego, make, model, year, engine, gb, odo, cond, primary, colour, body_type, club_reg, vtype) = spec
        v = Vehicle(
            user_id=user_id,
            nickname=nick, rego=rego, make=make, model=model, year=year,
            engine=engine, transmission=gb, odometer_km=odo,
            condition=cond, is_primary=primary,
            colour=colour, body_type=body_type, club_reg=club_reg,
            vehicle_type=vtype,
        )
        db.add(v)
        await db.flush()
        vehicles.append(v)

    # --- 6 years of services, fuel, mods, parts for each vehicle ---
    # Demo images (uploaded to MinIO once) reused for receipts/mods/services.
    demo_keys = {
        "fuel": "demo/fuel-receipt.png",
        "parts": "demo/parts-receipt.png",
        "service": "demo/service-invoice.png",
        "mod": "demo/mod-photo.png",
    }
    try:
        for dk in demo_keys:
            await _upload_demo_image(demo_keys[dk], (28, 96, 128) if dk == "mod" else (238, 238, 238))
    except Exception as exc:  # storage may be unavailable; demo still seeds
        logger.warning("demo_image_seed_failed", error=str(exc))

    for v, spec in zip(vehicles, specs):
        vid = v.id
        base_odo = spec[7]
        l100 = {  # typical L/100km per vehicle
            "Skyline R34": 12.2, "Family Commuter": 7.4, "Weekend MX-5": 8.1,
            "Tradie Hilux": 9.8, "Project Silvia": 11.3,
            "Ducati Monster": 5.6, "Kawasaki Ninja": 4.8,
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
            "Ducati Monster": ["Service + valve check", "Chain & sprockets", "Brake pads"],
            "Kawasaki Ninja": ["Scheduled service", "Chain kit", "Tyres"],
        }[spec[0]]
        for y in range(6):
            m = 6 - y
            svc_date = today - timedelta(days=int(m * 365) + rng.randint(0, 40))
            kind = rng.choice(["oil", "scheduled", "repair"])
            title = service_templates[y % len(service_templates)]
            cost = rng.choice([180, 320, 480, 650, 890, 1400, 2400])
            odo_at = base_odo - (6 - m) * rng.randint(9000, 13000)
            svc = ServiceRecord(
                vehicle_id=vid, service_date=svc_date, odometer_km=max(odo_at, 0),
                service_type=kind, description=title, workshop="AutoBrain AutoWorks",
                cost=float(cost), status="completed",
            )
            db.add(svc)
            await db.flush()
            item_sets = {
                "oil": [("Engine oil 5W-30", "part", 1, 42.0),
                        ("Oil filter", "part", 1, 14.0),
                        ("Oil-change labour", "labour", 1, 110.0)],
                "scheduled": [("Scheduled service labour", "labour", 1, 220.0),
                              ("Full inspection", "labour", 1, 60.0)],
                "repair": [("Parts (repair)", "part", 2, 95.0),
                           ("Repair labour", "labour", 3, 120.0)],
            }[kind]
            for iname, ikind, iqty, iunit in item_sets:
                db.add(ServiceItem(
                    service_id=svc.id, name=iname, quantity=iqty,
                    unit_cost=float(iunit), kind=ikind,
                ))
            if y == 0:
                svc.photo_keys = [demo_keys["service"]]
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
            "Ducati Monster": [("Termignoni exhaust", "performance", 2400),
                               ("Rizoma levers", "interior", 380)],
            "Kawasaki Ninja": [("Akrapovic slip-on", "exhaust", 1600),
                               ("Tail tidy", "exterior", 220)],
        }[spec[0]]
        for (mname, cat, mcost), k in zip(mods, range(len(mods))):
            db.add(Modification(
                vehicle_id=vid, name=mname, category=cat, cost=float(mcost),
                install_date=today - timedelta(days=(len(mods) - k) * 300),
                odometer_km=base_odo - (len(mods) - k) * 8000,
                notes="Demo modification record.",
                photo_keys=[demo_keys["mod"]] if k == 0 else None,
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

        # --- ATO logbook (skipped for club-registered vehicles) ---
        if not v.club_reg:
            trips = [
                ("Home", "Office", "work", "Commute to work"),
                ("Office", "Home", "work", "Commute home"),
                ("Home", "Bunnings Warehouse", "private", "Weekend errands"),
                ("Bunnings Warehouse", "Home", "private", "Weekend errands"),
                ("Home", "Workshop", "work", "Site visit"),
                ("Workshop", "Home", "work", "Return from site"),
                ("Home", "Supermarket", "private", "Grocery run"),
                ("Supermarket", "Home", "private", "Grocery run"),
                ("Home", "Gym", "private", "Morning workout"),
                ("Gym", "Home", "private", "Morning workout"),
            ]
            lb_odo = max(base_odo - 14000, 0)
            for ti, (sl, el, purpose, reason) in enumerate(trips):
                start_dt = (datetime.combine(today - timedelta(days=(len(trips) - ti) * 6),
                                             datetime.min.time())
                            + timedelta(hours=7 + (ti % 6)))
                end_dt = start_dt + timedelta(minutes=25 + rng.randint(5, 30))
                dist = rng.randint(8, 26)
                db.add(LogEntry(
                    vehicle_id=vid, started_at=start_dt, ended_at=end_dt,
                    start_odometer_km=lb_odo, end_odometer_km=lb_odo + dist,
                    distance_km=float(dist), purpose=purpose, reason=reason,
                    start_location=sl, end_location=el,
                    start_lat=-37.8 + rng.uniform(-0.04, 0.04),
                    start_lng=145.0 + rng.uniform(-0.04, 0.04),
                    status="completed",
                ))
                lb_odo += dist + rng.randint(0, 4)

        # --- scanned receipts (done) + extracted items; a Shell one links to fuel ---
        receipts = [
            ("Repco", [("Engine oil filter", "part", 1, 14.5), ("Brake pads (set)", "part", 1, 120.0)], 134.5),
            ("AutoBrain AutoWorks", [("Scheduled service labour", "labour", 1, 220.0), ("Inspection", "labour", 1, 60.0)], 280.0),
            ("Shell", [("Fuel — 95 RON", "part", 1, 85.0)], 85.0),
        ]
        fuel_logs = list((await db.scalars(
            select(FuelLog).where(FuelLog.vehicle_id == vid).order_by(FuelLog.fill_date.desc())
        )).all())
        for ri, (vendor, items, total) in enumerate(receipts):
            key = demo_keys["fuel"] if vendor == "Shell" else (demo_keys["parts"] if ri == 0 else demo_keys["service"])
            rdate = today - timedelta(days=ri * 40 + 5)
            rcp = Receipt(
                vehicle_id=vid, file_key=key,
                original_name=f"{vendor.lower().replace(' ', '-')}.png",
                content_type="image/png", ocr_status="done", vendor=vendor,
                total=float(total), currency="AUD", invoice_date=str(rdate),
                extracted=json.dumps({"vendor": vendor, "total": total, "items": items}),
            )
            db.add(rcp)
            await db.flush()
            for iname, ikind, iqty, iunit in items:
                db.add(ExtractedItem(receipt_id=rcp.id, kind=ikind, name=iname,
                                     quantity=iqty, unit_cost=float(iunit)))
            if vendor == "Shell" and fuel_logs:
                fuel_logs[ri].receipt_id = rcp.id

        # --- resale valuation snapshot ---
        est = {"Skyline R34": 68000, "Family Commuter": 24500, "Weekend MX-5": 16500,
               "Tradie Hilux": 21000, "Project Silvia": 15000,
               "Ducati Monster": 11000, "Kawasaki Ninja": 9000}[spec[0]]
        db.add(ValuationSnapshot(
            vehicle_id=vid, estimated_value=float(est),
            low=float(est * 0.85), high=float(est * 1.12), currency="AUD",
            factors=json.dumps({"condition": spec[8], "odometer_km": odo, "service_history": True}),
            recommendations=json.dumps(["Address minor paint chips", "Keep service history current"]),
        ))

        # --- diagnostics (one open, one resolved) ---
        diags = [
            ("Rough idle when cold, slight hesitation under load", "low", 350, "open",
             "Likely a dirty MAF sensor or vacuum leak — clean the MAF and check intake hoses."),
            ("Check-engine light P0301 — cylinder 1 misfire", "high", 480, "resolved",
             "Cylinder 1 misfire — likely a spark plug or ignition coil; coil replaced."),
        ]
        for dsymptoms, dseverity, dcost, dstatus, dsummary in diags:
            db.add(Diagnostic(
                vehicle_id=vid, symptoms=dsymptoms, severity=dseverity,
                estimated_cost=float(dcost), status=dstatus, summary=dsummary,
                ai_response=json.dumps({"summary": dsummary, "severity": dseverity,
                                        "estimated_cost": dcost}),
                resolved_at=datetime.now(timezone.utc) if dstatus == "resolved" else None,
            ))
