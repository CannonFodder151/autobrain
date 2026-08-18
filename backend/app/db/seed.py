"""Seed utilities: bootstrap admin + demo account and sample data."""

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
from app.social.models import (
    SocialBuild,
    SocialComment,
    SocialShareScope,
    get_server_config,
)

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
                from sqlalchemy import delete as _delete

                from app.social.models import SocialLike, SocialPhoto

                builds = list((await db.scalars(
                    select(SocialBuild.id).where(SocialBuild.vehicle_id.in_(vids))
                )).all())
                if builds:
                    await db.execute(_delete(SocialPhoto).where(SocialPhoto.build_id.in_(builds)))
                    await db.execute(_delete(SocialComment).where(SocialComment.build_id.in_(builds)))
                    await db.execute(_delete(SocialLike).where(SocialLike.build_id.in_(builds)))
                    await db.execute(_delete(SocialShareScope).where(SocialShareScope.build_id.in_(builds)))
                    await db.execute(_delete(SocialBuild).where(SocialBuild.id.in_(builds)))
                # Draft (build-less) uploads by the demo user
                await db.execute(_delete(SocialPhoto).where(SocialPhoto.uploader_user_id == user.id))
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
                # Shares involving the demo account (as vehicle owner or as
                # invitee) must go before the vehicle/user deletes, or the FK
                # (NO ACTION) blocks them and the reset crashes on Postgres.
                from app.models.share import VehicleShare

                await db.execute(
                    delete(VehicleShare).where(
                        (VehicleShare.vehicle_id.in_(vids))
                        | (VehicleShare.invitee_user_id == user.id)
                    )
                )
                await db.execute(delete(Vehicle).where(Vehicle.user_id == user.id))
            # Issues-blog content authored by the demo user (AUT-712): posts,
            # their replies and flags must go before the user delete (FK NO
            # ACTION would block the reset on Postgres). Other users' posts are
            # preserved.
            from app.social.models import SocialIssueComment, SocialIssueFlag, SocialIssuePost

            demo_post_ids = list((await db.scalars(
                select(SocialIssuePost.id).where(SocialIssuePost.author_user_id == user.id)
            )).all())
            if demo_post_ids:
                await db.execute(delete(SocialIssueFlag).where(SocialIssueFlag.post_id.in_(demo_post_ids)))
                await db.execute(delete(SocialIssueComment).where(SocialIssueComment.post_id.in_(demo_post_ids)))
                await db.execute(delete(SocialIssuePost).where(SocialIssuePost.id.in_(demo_post_ids)))
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

    await _seed_demo_social(db, user_id)
    await _seed_demo_issues(db, user_id)


async def _seed_demo_issues(db, user_id: str) -> None:
    """Seed the Community Garage issues blog: 16 demo posts with replies.

    Deterministic, human-readable help content (AUT-712). Tags come from the
    fixed vocabulary via detect_tags — no AI in the seed path. origin='demo'
    mirrors the demo builds; replies carry fictional display names with a null
    author_user_id (the federated-comment shape) so the blog looks lived-in
    without creating extra accounts. Idempotent: only runs on first seed / reset.
    """
    from app.social.models import SocialIssueComment, SocialIssuePost
    from app.social.snapshot import dumps
    from app.social.tags import detect_tags

    vehicles = {
        v.nickname: v
        for v in (await db.scalars(select(Vehicle).where(Vehicle.user_id == user_id))).all()
    }

    def _snapshot(nickname: str) -> dict | None:
        v = vehicles.get(nickname)
        if v is None:
            return None
        return {k: getattr(v, k) for k in ("make", "model", "year") if getattr(v, k)}

    # (nickname, days_ago, status, title, body, replies[(author, body, is_answer)])
    posts = [
        ("Skyline R34", 2, "resolved",
         "Rough idle and stalling on cold start",
         "Every cold morning the engine fires, runs rough for about 30 seconds, "
         "then sometimes stalls. Once warm it idles fine. No check-engine light. "
         "Coolant level is normal. Anyone had the same with the RB26?",
         [("TurboTom", "Check the idle air control valve — they gum up and stall cold starts.", False),
          ("MelbJDM", "Had the same. Cleaning the IACV fixed it for me.", False),
          ("NismoNick", "Mine was a dirty MAF sensor, engine ran lean until warm. Clean both, cheap fix.", True)]),
        ("Family Commuter", 5, "answered",
         "Spongy brake pedal after new pads",
         "Fitted new front brake pads over the weekend and bled the brakes, but the "
         "pedal is spongy and the car pulls slightly under heavy braking. Did I miss a step?",
         [("GarageGuru", "If the car pulls, a caliper may be sticking — grease the sliders.", False),
          ("PadQueen", "Re-bleed it. Air in the system feels exactly like this. Do the rears too.", True),
          ("TurboTom", "Also check the brake lines for a soft spot, common on 2020 Camrys.", False)]),
        ("Weekend MX-5", 8, "open",
         "Clutch pedal sticks halfway to the floor",
         "The clutch pedal sometimes sticks halfway down and only returns if I hook "
         "my foot under it. Fluid level is fine. This started after a track morning.",
         [("MelbJDM", "Sounds like the slave cylinder is failing, or the pedal pivot needs grease.", False),
          ("NismoNick", "Bleed the clutch. Old fluid boils on track days and causes exactly this.", False)]),
        ("Tradie Hilux", 11, "open",
         "Shudder when taking off in first gear",
         "There's a vibration through the whole car when I pull away in first, worse "
         "when the tray is loaded. Fine once moving. Clutch was replaced last year.",
         [("GarageGuru", "Check the engine mounts — loaded up they let the driveline bind.", False)]),
        ("Project Silvia", 3, "answered",
         "Turbo smoking after a track day",
         "After a hard track session the SR20 now puffs blue smoke under boost. Oil "
         "consumption is up but it doesn't smoke at idle. Turbo seals or rings?",
         [("TurboTom", "Blue smoke under boost only usually means turbo oil seals.", False),
          ("MelbJDM", "Pull the intake pipe and check for oil in the compressor housing — if it's oily, it's the turbo.", True)]),
        ("Skyline R34", 15, "resolved",
         "Overheats in traffic, fine on the highway",
         "The temp needle climbs in stop-start traffic but drops straight back down "
         "on the highway. Coolant is topped up, no leaks that I can see. Fans kick in late?",
         [("CoolantKing", "Test your radiator fan switch — late engagement is classic for this.", False),
          ("PadQueen", "Also worth flushing the cooling system; a clogged rad core does this.", False),
          ("GarageGuru", "Replaced the fan switch and flushed the radiator, no overheating since.", True)]),
        ("Family Commuter", 18, "answered",
         "Battery dies after sitting overnight",
         "If the car sits for more than a day the battery is flat. New battery six months "
         "ago. I've checked the interior lights are off. Parasitic drain?",
         [("SparkySam", "Definitely a parasitic drain. Measure current draw after the car sleeps.", False),
          ("NismoNick", "First thing I'd test is the alternator — a dying diode drains the battery.", False),
          ("SparkySam", "Found it: the boot light was staying on. 80 mA drain. Fixed.", True)]),
        ("Kawasaki Ninja", 21, "answered",
         "Front brake lever feels soft",
         "Front brake lever pulls almost to the bar since I topped up the fluid. Brakes "
         "feel mushy and the pads have plenty of life. Bleeding didn't change it.",
         [("BikeMike", "If bleeding didn't help, the master cylinder seals are likely gone.", False),
          ("CornerCrafter", "Top-up without a bleed often aerates the system — bleed it properly at the caliper.", True)]),
        ("Ducati Monster", 24, "open",
         "Clunk from the rear when shifting",
         "There's a metallic clunk and noise from the rear when I change gear, mostly on "
         "the up-shift. Chain looks tensioned correctly. Could it be the transmission "
         "mounts or the cush drive?",
         [("BikeMike", "Check cush drive rubbers in the rear sprocket carrier — they go soft.", False),
          ("CornerCrafter", "Could also be the chain out of alignment. Check both sprockets are straight.", False)]),
        ("Weekend MX-5", 27, "open",
         "Alternator whine in the stereo",
         "I get a whine that rises with engine rpm through the speakers. Only with the "
         "engine running. Aftermarket head unit installed last month.",
         [("SparkySam", "Classic earth loop — ground the head unit to the chassis at the same point as the battery.", False)]),
        ("Tradie Hilux", 30, "answered",
         "Steering wheel shakes at 110 km/h",
         "The steering wheel vibrates from about 110 km/h, smooth below that. New tyres "
         "recently. Wheel balance or steering linkage?",
         [("GarageGuru", "90% of the time after new tyres it's balance or a tight tyre fitment.", False),
          ("WheelWizard", "Rebalanced all four and the shake is gone. One wheel was 40g out.", True)]),
        ("Project Silvia", 33, "open",
         "Exhaust bangs on deceleration",
         "The exhaust pops and bangs when I back off in gear. Is this normal with the "
         "aftermarket cat-back or a sign of a lean condition?",
         [("MelbJDM", "Unburnt fuel igniting in the exhaust — common with free-flowing cat-backs.", False)]),
        ("Family Commuter", 36, "answered",
         "Air-con blows warm air",
         "The air-con blows warm air even on the coldest setting. The clutch engages "
         "and the system was regassed last summer. No obvious leaks.",
         [("CoolantKing", "If the compressor kicks in but it's warm, suspect the expansion valve or a partial block.", False),
          ("GarageGuru", "New expansion valve and a full service — cold air again.", True)]),
        ("Skyline R34", 39, "open",
         "Gearbox crunches into second",
         "Second gear crunches unless I double-clutch, and it gets worse when the box "
         "is warm. Synchro gone? The box has done 140k.",
         [("NismoNick", "Second-gear synchro, almost certainly. Common on the RB25 box.", False)]),
        ("Kawasaki Ninja", 42, "answered",
         "Tyres wearing unevenly on the edges",
         "The rear tyre is scrubbing on the outer edges only after 3,000 km. Pressure "
         "is correct. Suspension sag or too much camber?",
         [("CornerCrafter", "Edges only = under-inflation or sagging suspension. Set sag for your weight.", False),
          ("BikeMike", "Adjusted the rear preload and it's wearing evenly now.", True)]),
        ("Ducati Monster", 45, "open",
         "Oil leak from the front of the engine",
         "Fresh oil on the front of the engine after a long ride. Just changed the oil — "
         "could the filter or cooler line be weeping?",
         [("BikeMike", "Wipe it clean, run it warm, and chase the weep. Most likely the oil cooler line.", False)]),
    ]
    for nickname, days_ago, status, title, body, replies in posts:
        snapshot = _snapshot(nickname)
        post = SocialIssuePost(
            author_user_id=user_id,
            author_display_name=settings.DEMO_DISPLAY_NAME,
            server_name=None,
            title=title,
            body=body,
            vehicle_snapshot_json=dumps(snapshot) if snapshot else None,
            tags=detect_tags(title, body, snapshot),
            status=status,
            origin="demo",
            created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
        )
        db.add(post)
        await db.flush()
        answer_id = None
        for author, reply_body, is_answer in replies:
            comment = SocialIssueComment(
                post_id=post.id,
                author_user_id=None,
                author_display_name=author,
                server_name=None,
                body=reply_body,
                is_answer=is_answer,
            )
            db.add(comment)
            await db.flush()
            if is_answer:
                answer_id = comment.id
        if answer_id:
            post.resolved_comment_id = answer_id


async def _seed_demo_social(db, user_id: str) -> None:
    """Seed curated Community Garage demo builds (req 10): feature on, no hub.

    The demo server never registers with the federation hub — these builds are
    origin='demo' and are shown only on the demo instance.
    """
    cfg = await get_server_config(db)
    cfg.feature_enabled = True
    cfg.federation_enabled = False

    vehicles = list((await db.scalars(
        select(Vehicle).where(Vehicle.user_id == user_id, Vehicle.nickname.in_(
            ["Skyline R34", "Weekend MX-5", "Project Silvia", "Ducati Monster"]
        ))
    )).all())
    demos = [
        ("Skyline R34", "My weekend weapon — turbocharged and coilover'd since day one."),
        ("Weekend MX-5", "Slow car, fast fun. Enkei wheels + racing seat this season."),
        ("Project Silvia", "Long-term drift build. GT2871R goes in next month."),
        ("Ducati Monster", "Termignoni exhaust sounds unreal. Commuter for good weather only."),
    ]
    # Distinct photo colours per build so each feed item shows its own media.
    build_colours = {
        "Skyline R34": [(0, 61, 165), (28, 96, 128), (220, 20, 60)],
        "Weekend MX-5": [(178, 34, 34), (255, 99, 71), (70, 130, 180)],
        "Project Silvia": [(245, 245, 245), (105, 105, 105), (178, 34, 34)],
        "Ducati Monster": [(220, 20, 60), (30, 30, 30), (169, 169, 169)],
    }
    photo_keys: dict[str, list[str]] = {}
    try:
        for nickname, colours in build_colours.items():
            keys = []
            for i, rgb in enumerate(colours):
                key = f"demo/build-{nickname.lower().replace(' ', '-')}-{i + 1}.png"
                await _upload_demo_image(key, rgb)  # object key stored; URL signed at read time
                keys.append(key)
            photo_keys[nickname] = keys
    except Exception as exc:  # storage may be unavailable; demo still seeds
        logger.warning("demo_build_photo_seed_failed", error=str(exc))

    for nickname, caption in demos:
        vehicle = next((v for v in vehicles if v.nickname == nickname), None)
        if vehicle is None:
            continue
        build = SocialBuild(
            vehicle_id=vehicle.id,
            author_user_id=user_id,
            author_display_name=settings.DEMO_DISPLAY_NAME,
            server_name=None,
            title=nickname,
            caption=caption,
            origin="demo",
            snapshot_json="{}",
        )
        db.add(build)
        await db.flush()
        scope = SocialShareScope(
            build_id=build.id,
            allow_photos=True, allow_specs=True, allow_mods=True,
            allow_odometer=True, allow_notes=True,
        )
        db.add(scope)
        db.add(SocialComment(
            build_id=build.id,
            author_user_id=user_id,
            author_display_name=settings.DEMO_DISPLAY_NAME,
            body="Nice build! What's next on the list?",
        ))
    # At least 3 photos per build so every demo feed item shows media.
    from app.social.models import SocialPhoto

    for nickname, keys in photo_keys.items():
        vehicle = next((v for v in vehicles if v.nickname == nickname), None)
        if vehicle is None:
            continue
        build = await db.scalar(
            select(SocialBuild).where(SocialBuild.vehicle_id == vehicle.id)
        )
        if build is None:
            continue
        for key in keys:
            db.add(SocialPhoto(
                build_id=build.id,
                uploader_user_id=user_id,
                file_key=key,
                width=640,
                height=420,
            ))
