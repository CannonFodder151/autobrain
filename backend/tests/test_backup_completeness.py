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
os.environ["ADMIN_API_KEY"] = "test-admin-key-0123456789-0123456789"
os.environ["MARKET_DATA_URL"] = ""
os.environ["MARKET_DATA_API_KEY"] = ""

import pytest  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

# Self-contained sqlite engine so this file is immune to suite import order:
# the app's shared engine is created on first app import and pinned to whatever
# DATABASE_URL was set then, so reusing app.db.session.engine here could point
# at Postgres (OSError) if another module loaded first.
engine = create_async_engine("sqlite+aiosqlite:////tmp/autobrain-backup-test.db")
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

from app.db.session import Base  # noqa: E402
from app.models.share import VehicleShare  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.vehicle import Vehicle  # noqa: E402
from app.services.backup import dump_backup, load_backup, restore_all, serialize_all  # noqa: E402
from app.services.backup import _jsonable  # noqa: E402  (serialize-equivalent form for comparison)


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


class _FlakySession:
    """Delegates to a real session but fails the first execute with a
    transient OperationalError (closed connection), like a mid-deploy blip."""

    def __init__(self, inner: AsyncSession) -> None:
        self._inner = inner

    async def execute(self, *args, **kwargs):
        if not hasattr(self, "_failed"):
            self._failed = True
            raise OperationalError("stmt", {}, Exception("server closed the connection"))
        return await self._inner.execute(*args, **kwargs)

    async def rollback(self) -> None:
        return await self._inner.rollback()


@pytest.mark.asyncio
async def test_serialize_retries_transient_error() -> None:
    await _reset_schema()
    await _seed_share()
    async with SessionLocal() as db:
        data = await serialize_all(_FlakySession(db))
    assert set(data["data"]) == set(Base.metadata.tables)


def _seed_value(col, table_name: str) -> object:
    """Representative value per column type (covers every storage class)."""
    import datetime as _dt
    import uuid

    t = col.type
    from app.db.types import JSONList as _JSONList
    from app.db.types import StringArray as _StringArray

    name = type(t).__name__.lower()
    if isinstance(t, _JSONList):
        return ["a", "b"]
    if isinstance(t, _StringArray):
        return ["a", "b"]
    if isinstance(t, __import__("sqlalchemy").DateTime):
        return _dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=_dt.timezone.utc)
    if isinstance(t, __import__("sqlalchemy").Date):
        return _dt.date(2026, 1, 2)
    if "boolean" in name:
        return True
    if "integer" in name or "smallint" in name or "bigint" in name:
        return 1
    if "float" in name or "real" in name or "numeric" in name:
        return 1.5
    if "json" in name:
        return {"k": [1, 2]}
    return f"seed-{table_name}-{col.name}-{str(uuid.uuid4())[:8]}"


async def _seed_every_table() -> tuple[dict[str, list[dict]], dict[str, str]]:
    """Seed one representative row per table (FK-aware, fresh pks).

    Returns (expected rows keyed by table name, pk column name per table).
    server_default columns are excluded — the DB generates them freshly on
    restore, so they are not part of the equality comparison.
    """
    import uuid

    from datetime import date, datetime, timezone

    import sqlalchemy as sa

    pks: dict[str, list[object]] = {}
    expected: dict[str, list[dict]] = {}
    pks_by_table: dict[str, str] = {}
    pk_seq = iter(range(1, 10_000))
    async with SessionLocal() as db:
        for name in [t.name for t in Base.metadata.sorted_tables]:
            table = Base.metadata.tables[name]
            values: dict[str, object] = {}
            pk_col = next(c for c in table.columns if c.primary_key)
            pks_by_table[name] = pk_col.name
            if isinstance(pk_col.type, __import__("sqlalchemy").Integer):
                row_pk = next(pk_seq)
            else:
                row_pk = str(uuid.uuid4())
            for col in table.columns:
                if col.primary_key:
                    values[col.name] = row_pk
                    continue
                if col.server_default is not None:
                    continue  # DB-generated (created_at etc.)
                if col.foreign_keys:
                    fk = next(iter(col.foreign_keys))
                    target = fk.column.table.name
                    if target in pks:
                        values[col.name] = pks[target][0]
                    elif not col.nullable:
                        raise AssertionError(f"{name}.{col.name} FK target {target} unseeded")
                    continue
                values[col.name] = _seed_value(col, name)
            pks[name] = [row_pk]
            await db.execute(table.insert().values(**values))
            expected[name] = [dict(values)]
        await db.commit()
    return expected, pks_by_table


@pytest.mark.asyncio
async def test_full_schema_roundtrip_preserves_all_data() -> None:
    """Every table and column type survives serialize -> dump -> restore.

    Regression net for the AUT-696 backup-failure class: a column value that
    serializes one way but fails to reload (type coercion drift) would surface
    here as a restore error or a data mismatch (AUT-1023).
    """
    await _reset_schema()
    expected, pks_by_table = await _seed_every_table()

    async with SessionLocal() as db:
        snapshot = await serialize_all(db)
    payload = load_backup(dump_backup(snapshot))

    async with SessionLocal() as db:
        await restore_all(db, payload)
    async with SessionLocal() as db:
        restored = await serialize_all(db)

    rdata = restored["data"]
    assert set(rdata) == set(Base.metadata.tables)
    for name, rows in expected.items():
        assert name in rdata, f"restore dropped table {name}"
        assert len(rdata[name]) == len(rows), f"restore row-count mismatch for {name}"
        pk = pks_by_table[name]
        for row in rows:
            match = [r for r in rdata[name] if r.get(pk) == row[pk]]
            assert match, f"restore missing row {row[pk]} in {name}"
            for key, value in row.items():
                expect = _jsonable(value)
                got = match[0].get(key)
                if isinstance(expect, str) and isinstance(got, str):
                    # sqlite drops tz-offsets on read-back; compare instants.
                    try:
                        e = __import__("datetime").datetime.fromisoformat(expect)
                        g = __import__("datetime").datetime.fromisoformat(got)
                        if e.tzinfo is None:
                            e = e.replace(tzinfo=__import__("datetime").timezone.utc)
                        if g.tzinfo is None:
                            g = g.replace(tzinfo=__import__("datetime").timezone.utc)
                        if e == g:
                            continue
                    except ValueError:
                        pass
                assert expect == got, (
                    f"{name}.{key} mismatch: {value!r} != {got!r}"
                )
