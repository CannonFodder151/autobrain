"""Full-database backup/restore (admin only).

Serialises every table to a portable JSON snapshot — used by the admin
backup/restore endpoints, the scheduled daily backup, and server migration.
Restoring wipes existing data (admin-only operation) then re-inserts the
snapshot with original IDs, so foreign keys and relationships are preserved.
"""

import json
from datetime import datetime, timezone

import sqlalchemy
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
            await db.execute(table.insert().values(**_coerce_values(table, row)))
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
        if name == "vehicles":
            # Already fetched above, scoped to this user (the vehicles table has
            # user_id, not vehicle_id).
            data[name] = [{key: _jsonable(r[key]) for key in r.keys()} for r in vehicles]
            continue
        stmt = select(table)
        if "vehicle_id" in table.c:
            stmt = stmt.where(table.c.vehicle_id.in_(vehicle_ids))
        elif "user_id" in table.c:
            stmt = stmt.where(table.c.user_id == user_id)
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


def _coerce_values(table, row: dict) -> dict:
    """Rehydrate serialized values for a table insert.

    `_jsonable` stringifies datetimes/date, so on restore we parse them back to
    native types per the column definition before inserting.
    """
    from datetime import date, datetime

    values = {}
    for key, value in row.items():
        if value is None or key not in table.c:
            values[key] = value
            continue
        col_type = table.c[key].type
        if isinstance(col_type, (sqlalchemy.DateTime,)) and isinstance(value, str):
            values[key] = datetime.fromisoformat(value)
        elif isinstance(col_type, (sqlalchemy.Date,)) and isinstance(value, str):
            values[key] = date.fromisoformat(value[:10])
        else:
            values[key] = value
    return values


async def delete_user_complete(db: AsyncSession, user_id: str) -> None:
    """Delete a user and every row referencing them (vehicles, prefs, deliveries).

    The schema has no ON DELETE CASCADE, so user deletion must remove child
    rows explicitly or it fails with a foreign-key violation.
    """
    await _delete_user_data(db, user_id)
    await db.execute(
        _TABLES["notification_preferences"].delete().where(
            _TABLES["notification_preferences"].c.user_id == user_id
        )
    )
    vehicle_ids = list((await db.execute(
        select(_TABLES["vehicles"].c.id).where(_TABLES["vehicles"].c.user_id == user_id)
    )).scalars().all())
    if vehicle_ids:
        await db.execute(
            _TABLES["notification_deliveries"].delete().where(
                _TABLES["notification_deliveries"].c.vehicle_id.in_(vehicle_ids)
            )
        )
    await db.flush()
    await db.execute(_TABLES["users"].delete().where(_TABLES["users"].c.id == user_id))
    await db.commit()


async def _insert_profile_rows(db: AsyncSession, raw: dict, user_id: str) -> None:
    """Insert a profile's vehicles + child rows (from a serialized profile)."""
    for name in _VEHICLE_TABLES:
        table = _TABLES.get(name)
        if table is None:
            continue
        for row in raw.get(name, []):
            if name == "vehicles" and row.get("user_id") != user_id:
                continue
            # Skip tables owned purely by a user (not vehicle-scoped); those are
            # not part of a vehicle profile. Vehicles is handled above.
            if "user_id" in table.c and "vehicle_id" not in table.c and name != "vehicles":
                continue
            await db.execute(table.insert().values(**_coerce_values(table, row)))
    for name in ("service_items", "part_movements", "extracted_items"):
        for row in raw.get(name, []):
            await db.execute(_TABLES[name].insert().values(**_coerce_values(_TABLES[name], row)))


async def _delete_user_data(db: AsyncSession, user_id: str) -> None:
    """Delete all of a user's vehicles + child records (not the user row)."""
    vehicle_ids = list((await db.execute(
        select(_TABLES["vehicles"].c.id).where(_TABLES["vehicles"].c.user_id == user_id)
    )).scalars().all())
    if not vehicle_ids:
        return
    # Children first (reverse dependency order).
    for name in ("service_items", "obd_codes", "logbook_entries", "notification_preferences",
                 "valuation_snapshots", "extracted_items", "part_movements", "receipts",
                 "diagnostics", "modifications", "parts", "fuel_logs", "service_records",
                 "vehicle_events", "vehicles"):
        table = _TABLES.get(name)
        if table is None:
            continue
        if name == "part_movements":
            stmt = table.delete().where(
                table.c.part_id.in_(
                    select(_TABLES["parts"].c.id).where(_TABLES["parts"].c.vehicle_id.in_(vehicle_ids))
                )
            )
        elif name == "extracted_items":
            stmt = table.delete().where(
                table.c.receipt_id.in_(
                    select(_TABLES["receipts"].c.id).where(_TABLES["receipts"].c.vehicle_id.in_(vehicle_ids))
                )
            )
        elif name == "service_items":
            stmt = table.delete().where(
                table.c.service_id.in_(
                    select(_TABLES["service_records"].c.id).where(_TABLES["service_records"].c.vehicle_id.in_(vehicle_ids))
                )
            )
        else:
            # Vehicles table is owned by user_id; every other vehicle-scoped
            # table in the delete list has a vehicle_id column.
            if name == "vehicles":
                stmt = table.delete().where(table.c.user_id == user_id)
            else:
                stmt = table.delete().where(table.c.vehicle_id.in_(vehicle_ids))
        await db.execute(stmt)
    await db.flush()


async def restore_user_data(db: AsyncSession, user_id: str, data: dict) -> None:
    """Restore/override a user's profile data.

    Wipes the target user's existing vehicles + records and replaces them with
    the profile's data (original IDs preserved). User identity (email/password)
    stays the target account; user-level settings are updated from the profile.
    """
    raw = data.get("data") or {}
    users = raw.get("users") or []
    if not users:
        raise ValueError("Profile export contains no user")

    await _delete_user_data(db, user_id)
    await db.flush()

    # Apply user-level settings from the profile (not email/password/role).
    profile_user = users[0]
    allowed_user_fields = (
        "display_name", "max_vehicles", "free_account", "obd_enabled", "obd_auto_connect",
    )
    updates = {k: v for k, v in profile_user.items() if k in allowed_user_fields}
    if updates:
        await db.execute(
            _TABLES["users"].update().where(_TABLES["users"].c.id == user_id).values(**updates)
        )

    await _insert_profile_rows(db, raw, user_id)
    await db.commit()


async def import_user(db: AsyncSession, data: dict) -> str:
    """Import a profile export into the current instance.

    Returns the imported user id. If the user already exists (by email) the
    import is rejected; a new user is created from the profile.
    """
    raw = data.get("data") or {}
    users = raw.get("users") or []
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

    await _insert_profile_rows(db, raw, user_id)
    await db.commit()
    return user_id
