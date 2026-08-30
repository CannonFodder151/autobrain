"""Deterministic build snapshot from existing vehicles + mods data (no AI)."""

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mod import Modification
from app.models.vehicle import Vehicle
from app.social.models import SocialShareScope

# Share-scope defaults (req 11): minimal = photos + specs + mods.
_SCOPE_DEFAULTS = {
    "allow_photos": True,
    "allow_specs": True,
    "allow_mods": True,
    "allow_odometer": False,
    "allow_notes": False,
}


def _allowed(scope: SocialShareScope | None, field: str) -> bool:
    if scope is None:
        return bool(_SCOPE_DEFAULTS[field])
    value = getattr(scope, field, None)
    if value is None:  # unsaved instance: mapped_column defaults apply at flush
        return bool(_SCOPE_DEFAULTS[field])
    return bool(value)


async def build_snapshot(
    db: AsyncSession,
    vehicle: Vehicle,
    scope: SocialShareScope | None,
    photo_keys: list[str],
) -> dict:
    """Build the shareable snapshot (req 7): make/model + specs + mod list.

    Scope (req 11, default minimal = photos + specs + mods) redacts fields the
    user opted out of. Everything here is deterministic — existing DB rows only.
    """
    title = f"{vehicle.make or ''} {vehicle.model or ''}".strip() or vehicle.nickname
    snapshot: dict = {"title": title, "vehicle_type": vehicle.vehicle_type}

    if _allowed(scope, "allow_specs"):
        specs: dict = {}
        for field, value in (
            ("make", vehicle.make),
            ("model", vehicle.model),
            ("year", vehicle.year),
            ("colour", vehicle.colour),
            ("engine", vehicle.engine),
            ("transmission", vehicle.transmission),
            ("body_type", vehicle.body_type),
            ("condition", vehicle.condition),
        ):
            if value is not None:
                specs[field] = value
        if _allowed(scope, "allow_odometer"):
            specs["odometer_km"] = vehicle.odometer_km
        snapshot["specs"] = specs

    if _allowed(scope, "allow_notes"):
        snapshot["notes"] = _build_notes(vehicle)

    if _allowed(scope, "allow_mods"):
        mods = await _collect_mods(db, vehicle.id)
        snapshot["mods"] = mods

    if _allowed(scope, "allow_photos"):
        snapshot["photo_keys"] = photo_keys
    else:
        snapshot["photo_keys"] = []

    return snapshot


def _build_notes(vehicle: Vehicle) -> str:
    parts = [f"{vehicle.nickname}"]
    if vehicle.condition:
        parts.append(f"Condition: {vehicle.condition}")
    if vehicle.vehicle_type:
        parts.append(f"Type: {vehicle.vehicle_type}")
    return " — ".join(parts)


async def _collect_mods(db: AsyncSession, vehicle_id: str) -> list[dict]:
    rows = await db.scalars(
        select(Modification)
        .where(Modification.vehicle_id == vehicle_id)
        .order_by(Modification.install_date.asc())
    )
    mods = []
    for mod in rows:
        entry: dict = {"name": mod.name}
        if mod.category:
            entry["category"] = mod.category
        if mod.brand:
            entry["brand"] = mod.brand
        mods.append(entry)
    return mods


def dumps(snapshot: dict) -> str:
    return json.dumps(snapshot, ensure_ascii=False)


def loads(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        result = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return result if isinstance(result, dict) else {}
