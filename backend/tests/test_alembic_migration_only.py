"""AUT-5088: prove `alembic upgrade head` is the real schema path.

Hosted booted straight into ``python -m app.db.bootstrap``, whose ``create_all``
fallback swallowed every migration failure, so migration-only changes (new
index, constraint, column rename, data backfill) were dead code in production.
Static compose guards catch a deleted ``alembic upgrade head``; this module
catches the other half — a chain that no longer upgrades a hosted-shaped
database, or a data-only revision that stopped doing anything.

Both cases start from the shape hosted actually has: the schema built by the
``create_all`` fallback, ``alembic_version`` stamped but not advanced.

Each case builds its own throwaway database from ``ALEMBIC_TEST_ADMIN_URL``
(``postgresql://user:pass@host:5432/postgres``) and runs the real ``alembic``
CLI against it, so nothing here needs the dev or hosted stack. Skipped when
that variable is unset; the ``alembic-migrations`` CI job sets it against a
``pgvector/pgvector:pg17`` service, matching the hosted postgres image.
"""
import asyncio
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
ADMIN_URL = os.environ.get("ALEMBIC_TEST_ADMIN_URL", "")

pytestmark = pytest.mark.skipif(
    not ADMIN_URL, reason="ALEMBIC_TEST_ADMIN_URL not set (no throwaway postgres)"
)

def _head() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return ScriptDirectory.from_config(cfg).get_current_head()

def _async_dsn(dsn: str) -> str:
    """The app only has asyncpg installed, so the URL needs the async driver."""
    return (
        dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
        if dsn.startswith("postgresql://")
        else dsn
    )

def _alembic(dsn: str, *args: str) -> None:
    """Run the real alembic CLI against `dsn`."""
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": _async_dsn(dsn)},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"alembic {' '.join(args)} failed:\n{proc.stdout[-2000:]}\n{proc.stderr[-4000:]}"
    )

async def _sql(dsn: str, query: str, *args):
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        return await conn.fetchval(query, *args)
    finally:
        await conn.close()

async def _exec(dsn: str, query: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(query)
    finally:
        await conn.close()

@pytest.fixture()
def fresh_db():
    """Create an empty database, yield its DSN, drop it afterwards."""
    name = f"autotest_{uuid.uuid4().hex[:12]}"
    dsn = ADMIN_URL.rsplit("/", 1)[0] + "/" + name

    async def create() -> None:
        await _exec(ADMIN_URL, f'CREATE DATABASE "{name}"')

    asyncio.run(create())
    try:
        yield dsn
    finally:
        asyncio.run(_exec(ADMIN_URL, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))

def _run_app(dsn: str, code: str) -> None:
    """Run a snippet against `dsn` in a child process holding real app settings."""
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": _async_dsn(dsn)},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"failed: {proc.stderr[-2000:]}"

def _create_all(dsn: str) -> None:
    """Build a schema the way `app.db.bootstrap`'s fallback does."""
    _run_app(dsn, "import asyncio; from app.db.session import init_db; asyncio.run(init_db())")

def test_hosted_shaped_database_reaches_head(fresh_db):
    """A create_all-built database at the hosted stamp must reach head.

    This is the hosted shape exactly: the schema was built by the bootstrap
    fallback, `alembic_version` was stamped at `aut4925_missing_tables` and
    never advanced. After the AUT-5088 compose fix the boot runs
    `alembic upgrade head`, so the version has to land on head — which is the
    only way a migration-only change can ever reach production again.
    """
    _create_all(fresh_db)
    _alembic(fresh_db, "stamp", "aut4925_missing_tables")
    _alembic(fresh_db, "upgrade", "head")
    assert asyncio.run(_sql(fresh_db, "select version_num from alembic_version")) == _head()

def test_pending_revision_actually_applies(fresh_db):
    """The pending revision must run DDL, not be skipped as "already there".

    Hosted sits at `aut4925_missing_tables` with head `aut3448_fuel_price_snapshots`.
    Drop the table that head creates, then upgrade: the revision has to build it.
    That is the difference between a boot that applies migrations and a boot that
    just bumps a version string — and it is exactly why `fuel_price_snapshots`
    had no migration history until AUT-3005.
    """
    _create_all(fresh_db)
    _alembic(fresh_db, "stamp", "aut4925_missing_tables")
    asyncio.run(_exec(fresh_db, "DROP TABLE IF EXISTS fuel_price_snapshots"))
    _alembic(fresh_db, "upgrade", "head")
    assert asyncio.run(
        _sql(fresh_db, "select to_regclass('public.fuel_price_snapshots') is not null")
    ), "head revision did not create fuel_price_snapshots"
    assert asyncio.run(_sql(fresh_db, "select version_num from alembic_version")) == _head()


def test_downgrade_keeps_a_pre_existing_vehicle_type_column(fresh_db):
    """AUT-5612: a rollback must not drop a column ``upgrade()`` never added.

    This revision exists to repair the hosted ``create_all`` drift, where
    ``devices.vehicle_type`` is *already there* and ``upgrade()`` is a no-op. The
    old ``downgrade()`` dropped it anyway — data loss on exactly the database the
    migration targets. Roll the head revision back and the column must survive.
    """
    _create_all(fresh_db)
    _alembic(fresh_db, "stamp", "aut4925_missing_tables")
    _alembic(fresh_db, "upgrade", "head")
    _alembic(fresh_db, "downgrade", "-1")
    assert asyncio.run(
        _sql(
            fresh_db,
            "select exists(select 1 from information_schema.columns "
            "where table_name='devices' and column_name='vehicle_type')",
        )
    ), "AUT-5612: downgrade dropped a pre-existing devices.vehicle_type"


def test_downgrade_drops_the_column_this_revision_created(fresh_db):
    """AUT-5612: the guard must not neuter a real rollback.

    Mirror image: drop the column first so ``upgrade()`` genuinely creates it
    (stamping the provenance marker), then ``downgrade()`` has to remove it —
    otherwise every future rollback silently no-ops.
    """
    _create_all(fresh_db)
    _alembic(fresh_db, "stamp", "aut4925_missing_tables")
    asyncio.run(_exec(fresh_db, "ALTER TABLE devices DROP COLUMN IF EXISTS vehicle_type"))
    _alembic(fresh_db, "upgrade", "head")
    assert asyncio.run(
        _sql(
            fresh_db,
            "select col_description('devices'::regclass, attnum) from pg_attribute "
            "where attrelid='devices'::regclass and attname='vehicle_type'",
        )
    ), "upgrade() did not stamp the provenance marker on the column it created"
    _alembic(fresh_db, "downgrade", "-1")
    assert not asyncio.run(
        _sql(
            fresh_db,
            "select exists(select 1 from information_schema.columns "
            "where table_name='devices' and column_name='vehicle_type')",
        )
    ), "downgrade() refused to drop the column this revision created"
