"""Backup completeness + restore roundtrip (AUT-521 regression).

The full-DB snapshot used to be driven by a hand-maintained table list that
drifted from the ORM metadata: `market_listing_cache`, `revoked_refresh_tokens`
were missing entirely, and `vehicle_shares` was only added on 2026-08-10. A
snapshot taken by such a build, restored by newer code, deleted the missing
tables' rows without re-inserting them — which is how shared vehicles could be
silently wiped during a server upgrade/restore.

Run (sqlite, no Postgres needed):
    cd backend && python3 -m pytest tests/test_backup_completeness.py -q
"""

import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:////tmp/autobrain-backup-test.db"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["POSTGRES_USER"] = "autobrain"
os.environ["POSTGRES_PASSWORD"] = "autobrain"
os.environ["POSTGRES_DB"] = "autobrain"
os.environ["MINIO_ACCESS_KEY"] = "autobrain"
os.environ["MINIO_SECRET_KEY"] = "autobrain"
os.environ["MINIO_BUCKET"] = "autobrain-assets"
os.environ["MINIO_ENDPOINT"] = "minio:9000"
os.environ["AI_GATEWAY_API_KEY"] = "test-ai-key"
os.environ["ADMIN_API_KEY"] = "test-admin-key"
os.environ["MARKET_DATA_URL"] = ""
os.environ["MARKET_DATA_API_KEY"] = ""

import pytest  # noqa: E402

from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.models.share import VehicleShare  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.vehicle import Vehicle  # noqa: E402
from app.services.backup import dump_backup, load_backup, restore_all, serialize_all  # noqa: E402


async def _reset_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


async def _seed_share() -> None:
    async with SessionLocal() as db:
        owner = User(
            email="owner@example.com",
            display_name="Owner",
            hashed_password="x",
            max_vehicles=3,
        )
        invitee = User(
            email="invitee@example.com",
            display_name="Invitee",
            hashed_password="x",
            max_vehicles=3,
        )
        db.add_all([owner, invitee])
        await db.flush()
        vehicle = Vehicle(user_id=owner.id, nickname="Shared whip")
        db.add(vehicle)
        await db.flush()
        db.add(VehicleShare(vehicle_id=vehicle.id, invitee_user_id=invitee.id))
        await db.commit()


@pytest.mark.asyncio
async def test_serialize_covers_every_table() -> None:
    await _reset_schema()
    await _seed_share()
    async with SessionLocal() as db:
        data = await serialize_all(db)
    snapshot = data["data"]
    assert set(snapshot) == set(Base.metadata.tables), (
        f"snapshot missing tables: {set(Base.metadata.tables) - set(snapshot)}"
    )
    assert len(snapshot["vehicle_shares"]) == 1


@pytest.mark.asyncio
async def test_restore_roundtrip_keeps_shares() -> None:
    await _reset_schema()
    await _seed_share()
    async with SessionLocal() as db:
        snapshot = await serialize_all(db)
    payload = load_backup(dump_backup(snapshot))

    async with SessionLocal() as db:
        await restore_all(db, payload)
    async with SessionLocal() as db:
        shares = (await db.execute(VehicleShare.__table__.select())).mappings().all()
    assert len(shares) == 1
