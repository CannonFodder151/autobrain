"""Full-database backup/restore (admin only).

Serialises every table to a portable JSON snapshot — used by the admin
backup/restore endpoints, the scheduled daily backup, and server migration.
Restoring wipes existing data (admin-only operation) then re-inserts the
snapshot with original IDs, so foreign keys and relationships are preserved.
"""

import json
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import Base

logger = get_logger(__name__)

# Tables are ordered parent-first for insertion and reversed for deletion.
_ORDER = [
    "users",
    "vehicles",
    "vehicle_events",
    "service_records",
    "service_items",
    "fuel_logs",
    "diagnostics",
    "modifications",
    "parts",
    "part_movements",
    "receipts",
    "extracted_items",
    "valuation_snapshots",
    "notification_preferences",
    "notification_deliveries",
    "logbook_entries",
    "obd_codes",
]

_TABLES = {name: table for name, table in Base.metadata.tables.items()}


def _jsonable(value):
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except TypeError:
            return str(value)
    return value


async def serialize_all(db: AsyncSession) -> dict:
    """Serialize every table into a JSON-ready dict."""
    data: dict[str, list[dict]] = {}
    for name in _ORDER:
        table = _TABLES.get(name)
        if table is None:
            continue
        rows = (await db.execute(select(table))).mappings().all()
        data[name] = [
            {key: _jsonable(row[key]) for key in row.keys()} for row in rows
        ]
    return {
        "app": "autobrain",
        "kind": "backup",
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }


def dump_backup(data: dict) -> bytes:
    return json.dumps(data, indent=2).encode("utf-8")


def load_backup(raw: bytes) -> dict:
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict) or data.get("app") != "autobrain" or data.get("kind") != "backup":
        raise ValueError("Not an AutoBrain backup file")
    return data


async def restore_all(db: AsyncSession, data: dict) -> None:
    """Wipe the database and re-insert the snapshot. Admin-only operation."""
    if not isinstance(data.get("data"), dict):
        raise ValueError("Backup file has no data")

    # Delete children-first.
    for name in reversed(_ORDER):
        table = _TABLES.get(name)
        if table is not None:
            await db.execute(delete(table))
    await db.flush()

    for name in _ORDER:
        table = _TABLES.get(name)
        if table is None:
            continue
        for row in data["data"].get(name, []):
            await db.execute(table.insert().values(**row))
    await db.commit()
    logger.info("restore_completed", tables=len(_ORDER))


# --- user-scoped profile export (data portability) ---
# vehicle-scoped tables: (table, vehicle_col). Tables without a direct vehicle
# column are reached through a parent id via _via.
_VEHICLE_TABLES = [
    "vehicles", "vehicle_events", "service_records", "fuel_logs",
    "diagnostics", "modifications", "parts", "receipts",
    "valuation_snapshots", "notification_preferences", "logbook_entries", "obd_codes",
]


async def serialize_user(db: AsyncSession, user_id: str) -> dict:
    """Serialize one user + all their vehicles and data (profile export)."""
    vehicles = list((await db.execute(
        select(_TABLES["vehicles"]).where(_TABLES["vehicles"].c.user_id == user_id)
    )).mappings().all())
    vehicle_ids = {v["id"] for v in vehicles}
    data: dict[str, list[dict]] = {}
    data["users"] = [
        {key: _jsonable(r[key]) for key in r.keys()}
        for r in (await db.execute(
            select(_TABLES["users"]).where(_TABLES["users"].c.id == user_id)
        )).mappings().all()
    ]
    for name in _VEHICLE_TABLES:
        table = _TABLES.get(name)
        if table is None:
            continue
        stmt = select(table)
        if "vehicle_id" in table.c:
            stmt = stmt.where(table.c.vehicle_id.in_(vehicle_ids))
        rows = (await db.execute(stmt)).mappings().all()
        data[name] = [{key: _jsonable(r[key]) for key in r.keys()} for r in rows]

    # Children without a direct vehicle_id: service_items, part_movements, extracted_items.
    si = _TABLES["service_records"]
    rows = (await db.execute(
        select(_TABLES["service_items"]).where(
            _TABLES["service_items"].c.service_id.in_(
                select(si.c.id).where(si.c.vehicle_id.in_(vehicle_ids))
            )
        )
    )).mappings().all()
    data["service_items"] = [{key: _jsonable(r[key]) for key in r.keys()} for r in rows]

    pm = _TABLES["parts"]
    rows = (await db.execute(
        select(_TABLES["part_movements"]).where(
            _TABLES["part_movements"].c.part_id.in_(
                select(pm.c.id).where(pm.c.vehicle_id.in_(vehicle_ids))
            )
        )
    )).mappings().all()
    data["part_movements"] = [{key: _jsonable(r[key]) for key in r.keys()} for r in rows]

    rc = _TABLES["receipts"]
    rows = (await db.execute(
        select(_TABLES["extracted_items"]).where(
            _TABLES["extracted_items"].c.receipt_id.in_(
                select(rc.c.id).where(rc.c.vehicle_id.in_(vehicle_ids))
            )
        )
    )).mappings().all()
    data["extracted_items"] = [{key: _jsonable(r[key]) for key in r.keys()} for r in rows]

    return {
        "app": "autobrain",
        "kind": "profile",
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }


async def import_user(db: AsyncSession, data: dict) -> str:
    """Import a profile export into the current instance.

    Returns the imported user id. If the user already exists (by email) the
    import is rejected; a new user is created from the profile.
    """
    raw = data.get("data") or {}
    users = raw.get("users") or []
    vehicles = raw.get("vehicles") or []
    if not users:
        raise ValueError("Profile export contains no user")
    user_row = users[0]
    email = user_row.get("email")
    if not email:
        raise ValueError("Profile export has no email")

    existing = await db.scalar(select(_TABLES["users"].c.id).where(_TABLES["users"].c.email == email))
    if existing:
        raise ValueError(f"An account for {email} already exists on this server")

    user_id = user_row["id"]
    await db.execute(_TABLES["users"].insert().values(**user_row))
    await db.flush()

    vehicle_ids = {v["id"] for v in vehicles}
    for name in _VEHICLE_TABLES:
        table = _TABLES.get(name)
        if table is None:
            continue
        for row in raw.get(name, []):
            if name == "vehicles" and row.get("user_id") != user_id:
                continue
            if "user_id" in table.c and name != "vehicles":
                continue
            await db.execute(table.insert().values(**row))
    for name in ("service_items", "part_movements", "extracted_items"):
        for row in raw.get(name, []):
            await db.execute(_TABLES[name].insert().values(**row))
    await db.commit()
    return user_id
